"""Authenticated, request-scoped Visual Inspection endpoint contract tests."""

import asyncio
import json
import subprocess
import sys
import threading
import textwrap
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from app.api import routes
from app.core.config import Settings
from app.models.db import (
    Analysis,
    AnalysisFailureLog,
    Listing,
    RiskIndicator,
    SessionLocal,
    User,
)
from app.schemas.schemas import ListingIn, RiskLevel
from app.services import visual_inspection
from app.services.visual_inspection import (
    VisualInspectionResult,
    VisualInspectionServiceUnavailable,
)
from app.services.visual_inspection_images import NormalizedVisualImage


VISUAL_INSPECTION_PATH = "/api/analyses/{analysis_id}/visual-inspection"
MAX_COMBINED_SOURCE_BYTES = 10 * 1024 * 1024
OFFLOAD_PROGRESS_TIMEOUT_SECONDS = 0.5
OFFLOAD_REQUEST_TIMEOUT_SECONDS = 3.0

SAFE_LISTING = {
    "title": "IKEA Billy bookcase, white",
    "price": 450.0,
    "currency": "ZAR",
    "source": "Facebook Marketplace",
    "description": "Used bookcase in good condition, collection in Randburg.",
}


def _register_and_login(client, email: str = "alice@example.com") -> dict[str, str]:
    registration = client.post(
        "/api/auth/register",
        json={"email": email, "name": "Visual Test User", "password": "s3curepass"},
    )
    assert registration.status_code == 201

    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "s3curepass"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _create_analysis(client, headers: dict[str, str]) -> dict:
    response = client.post("/api/analyses", json=SAFE_LISTING, headers=headers)
    assert response.status_code == 201
    return response.json()


def _jpeg_bytes(color: tuple[int, int, int] = (32, 96, 160)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (24, 16), color).save(output, format="JPEG")
    return output.getvalue()


def _photos(count: int) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        (
            "photos",
            (f"photo-{number}.jpg", _jpeg_bytes((32 * number, 64, 96)), "image/jpeg"),
        )
        for number in range(1, count + 1)
    ]


def _result(
    observation: str = "Photo 1 visibly shows a scratch on the upper-right corner.",
    photo_numbers: list[int] | None = None,
) -> VisualInspectionResult:
    return VisualInspectionResult.model_validate(
        {
            "findings": [
                {
                    "category": "visible_damage",
                    "observation": observation,
                    "photo_numbers": [1] if photo_numbers is None else photo_numbers,
                }
            ]
        }
    )


class _FakeVisualInspectionProvider:
    def __init__(self, result: VisualInspectionResult) -> None:
        self.result = result
        self.calls: list[tuple[NormalizedVisualImage, ...]] = []
        self.listing_contexts = []

    def inspect(
        self,
        images: list[NormalizedVisualImage],
        listing,
    ) -> VisualInspectionResult:
        self.calls.append(tuple(images))
        self.listing_contexts.append(listing)
        return self.result


def _install_provider(monkeypatch, provider: _FakeVisualInspectionProvider) -> None:
    monkeypatch.setattr(
        routes,
        "get_visual_inspection_service",
        lambda _settings: provider,
    )


def _database_counts() -> dict[str, int]:
    db = SessionLocal()
    try:
        return {
            "users": db.query(User).count(),
            "listings": db.query(Listing).count(),
            "analyses": db.query(Analysis).count(),
            "risk_indicators": db.query(RiskIndicator).count(),
            "analysis_failure_logs": db.query(AnalysisFailureLog).count(),
        }
    finally:
        db.close()


async def _request_visual_inspection_with_health_probe(
    client,
    headers: dict[str, str],
    analysis_id: int,
    blocking_started: threading.Event,
    release_blocker: threading.Event,
):
    loop = asyncio.get_running_loop()
    allow_health_request = asyncio.Event()
    health_completed = threading.Event()
    health_progressed_before_release: list[bool] = []

    def release_after_health_probe() -> None:
        started_in_time = blocking_started.wait(
            timeout=OFFLOAD_PROGRESS_TIMEOUT_SECONDS
        )
        loop.call_soon_threadsafe(allow_health_request.set)
        progressed = started_in_time and health_completed.wait(
            timeout=OFFLOAD_PROGRESS_TIMEOUT_SECONDS
        )
        health_progressed_before_release.append(progressed)
        release_blocker.set()

    controller = threading.Thread(target=release_after_health_probe, daemon=True)
    controller.start()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app),
            base_url="http://testserver",
        ) as async_client:

            async def request_health():
                await allow_health_request.wait()
                response = await async_client.get("/api/health")
                health_completed.set()
                return response

            visual_request = asyncio.create_task(
                async_client.post(
                    VISUAL_INSPECTION_PATH.format(analysis_id=analysis_id),
                    headers=headers,
                    files=_photos(1),
                )
            )
            health_request = asyncio.create_task(request_health())
            visual_response, health_response = await asyncio.wait_for(
                asyncio.gather(visual_request, health_request),
                timeout=OFFLOAD_REQUEST_TIMEOUT_SECONDS,
            )
    finally:
        release_blocker.set()
        controller.join(timeout=OFFLOAD_PROGRESS_TIMEOUT_SECONDS)

    assert not controller.is_alive()
    return visual_response, health_response, health_progressed_before_release


def test_visual_inspection_requires_authentication(client):
    response = client.post(
        VISUAL_INSPECTION_PATH.format(analysis_id=1),
        files=_photos(1),
    )

    assert response.status_code == 401


def test_visual_inspection_hides_another_users_analysis(client, monkeypatch):
    owner_headers = _register_and_login(client, "owner@example.com")
    analysis = _create_analysis(client, owner_headers)
    other_headers = _register_and_login(client, "other@example.com")
    provider = _FakeVisualInspectionProvider(_result())
    _install_provider(monkeypatch, provider)

    response = client.post(
        VISUAL_INSPECTION_PATH.format(analysis_id=analysis["id"]),
        headers=other_headers,
        files=_photos(1),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Analysis not found"}
    assert provider.calls == []


def test_visual_inspection_returns_404_for_unknown_analysis(client, monkeypatch):
    headers = _register_and_login(client)
    provider = _FakeVisualInspectionProvider(_result())
    _install_provider(monkeypatch, provider)

    response = client.post(
        VISUAL_INSPECTION_PATH.format(analysis_id=999_999),
        headers=headers,
        files=_photos(1),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Analysis not found"}
    assert provider.calls == []


def test_visual_inspection_422_mapping_does_not_require_new_starlette_symbol():
    probe = textwrap.dedent(
        """
        import asyncio
        from types import SimpleNamespace

        from fastapi import HTTPException
        from starlette import status

        status.__dict__.pop("HTTP_422_UNPROCESSABLE_CONTENT", None)

        from app.api import routes

        assert routes._VISUAL_IMAGE_ERROR_STATUS["invalid_image"] == 422
        assert routes._VISUAL_IMAGE_ERROR_STATUS["animated_image"] == 422

        class FakeQuery:
            def join(self, *_args):
                return self

            def filter(self, *_args):
                return self

            def options(self, *_args):
                return self

            def first(self):
                return SimpleNamespace(listing=SimpleNamespace())

        class FakeDatabase:
            def query(self, *_args):
                return FakeQuery()

        try:
            asyncio.run(
                routes.create_visual_inspection(
                    analysis_id=1,
                    photos=[],
                    db=FakeDatabase(),
                    user=SimpleNamespace(id=1),
                )
            )
        except HTTPException as exc:
            assert exc.status_code == 422
            assert exc.detail == "photo_count_out_of_range"
        else:
            raise AssertionError("zero-photo request did not return HTTP 422")
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("photo_count", [0, 4])
def test_visual_inspection_requires_one_to_three_photos(
    client,
    monkeypatch,
    photo_count,
):
    headers = _register_and_login(client)
    analysis = _create_analysis(client, headers)
    provider = _FakeVisualInspectionProvider(_result())
    _install_provider(monkeypatch, provider)

    response = client.post(
        VISUAL_INSPECTION_PATH.format(analysis_id=analysis["id"]),
        headers=headers,
        files=_photos(photo_count),
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "photo_count_out_of_range"}
    assert provider.calls == []


def test_visual_inspection_rejects_combined_source_bytes_before_normalization(
    client,
    monkeypatch,
):
    headers = _register_and_login(client)
    analysis = _create_analysis(client, headers)
    provider = _FakeVisualInspectionProvider(_result())
    _install_provider(monkeypatch, provider)

    def fail_if_normalization_is_attempted(*_args, **_kwargs):
        raise AssertionError("combined byte overflow reached image normalization")

    monkeypatch.setattr(
        routes,
        "normalize_visual_image",
        fail_if_normalization_is_attempted,
        raising=False,
    )
    payload_size = MAX_COMBINED_SOURCE_BYTES // 3 + 1
    files = [
        ("photos", (f"photo-{number}.jpg", b"x" * payload_size, "image/jpeg"))
        for number in range(1, 4)
    ]

    response = client.post(
        VISUAL_INSPECTION_PATH.format(analysis_id=analysis["id"]),
        headers=headers,
        files=files,
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "combined_images_too_large"}
    assert provider.calls == []


def test_visual_inspection_maps_image_rejection_to_a_safe_client_error(
    client,
    monkeypatch,
):
    headers = _register_and_login(client)
    analysis = _create_analysis(client, headers)
    provider = _FakeVisualInspectionProvider(_result())
    _install_provider(monkeypatch, provider)
    private_filename = "private-owner-name.gif"

    response = client.post(
        VISUAL_INSPECTION_PATH.format(analysis_id=analysis["id"]),
        headers=headers,
        files=[("photos", (private_filename, b"GIF89a", "image/gif"))],
    )

    assert response.status_code == 415
    assert response.json() == {"detail": "unsupported_type"}
    assert private_filename not in response.text
    assert provider.calls == []


@pytest.mark.parametrize("photo_count", [1, 3])
def test_visual_inspection_returns_only_a_transient_advisory_result(
    client,
    monkeypatch,
    photo_count,
):
    headers = _register_and_login(client)
    analysis = _create_analysis(client, headers)
    accepted = _result(photo_numbers=list(range(1, photo_count + 1)))
    provider = _FakeVisualInspectionProvider(accepted)
    _install_provider(monkeypatch, provider)
    detail_before = client.get(
        f"/api/analyses/{analysis['id']}",
        headers=headers,
    ).json()
    history_before = client.get("/api/analyses", headers=headers).json()
    counts_before = _database_counts()

    response = client.post(
        VISUAL_INSPECTION_PATH.format(analysis_id=analysis["id"]),
        headers=headers,
        files=_photos(photo_count),
    )

    assert response.status_code == 200
    assert response.json() == accepted.model_dump(mode="json")
    assert set(response.json()) == {"findings"}
    assert not {
        "risk_score",
        "risk_level",
        "recommendation",
        "price_plausibility",
    }.intersection(response.json())
    assert len(provider.calls) == 1
    assert provider.listing_contexts[0].title == SAFE_LISTING["title"]
    normalized_images = provider.calls[0]
    assert len(normalized_images) == photo_count
    assert all(image.mime_type == "image/jpeg" for image in normalized_images)
    assert all(image.data.startswith(b"\xff\xd8") for image in normalized_images)
    assert client.get(f"/api/analyses/{analysis['id']}", headers=headers).json() == detail_before
    assert client.get("/api/analyses", headers=headers).json() == history_before
    assert _database_counts() == counts_before


def test_visual_inspection_fails_closed_on_unsupported_generated_evidence(
    client,
    monkeypatch,
):
    headers = _register_and_login(client)
    analysis = _create_analysis(client, headers)
    offending_prose = "The photographed item is definitely counterfeit."
    provider = _FakeVisualInspectionProvider(_result(offending_prose))
    _install_provider(monkeypatch, provider)
    counts_before = _database_counts()

    response = client.post(
        VISUAL_INSPECTION_PATH.format(analysis_id=analysis["id"]),
        headers=headers,
        files=_photos(1),
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "visual_evidence_policy_violation"}
    assert offending_prose not in response.text
    assert len(provider.calls) == 1
    assert _database_counts() == counts_before


class _OpenAIResponse:
    def __init__(self, result: dict | None = None, status_code: int = 200) -> None:
        self._result = result or _result().model_dump(mode="json")
        self._response = httpx.Response(
            status_code,
            request=httpx.Request(
                "POST",
                "https://api.openai.com/v1/chat/completions",
            ),
            json={"error": {"message": "private-provider-body"}},
        )

    def raise_for_status(self) -> None:
        self._response.raise_for_status()

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(self._result),
                    }
                }
            ]
        }


class _RecordingPost:
    def __init__(self, *responses: _OpenAIResponse) -> None:
        self._responses = iter(responses)
        self.calls: list[dict] = []

    def __call__(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return next(self._responses)


class _UnexpectedPost:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        raise AssertionError("unconfigured visual inspection attempted HTTP")


def _visual_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def _route_settings(monkeypatch, **overrides) -> SimpleNamespace:
    values = routes.settings.model_dump()
    values.update(overrides)
    configured = SimpleNamespace(**values)
    monkeypatch.setattr(routes, "settings", configured)
    return configured


def _visual_service(settings: Settings):
    factory = getattr(
        visual_inspection,
        "get_visual_inspection_service",
    )
    return factory(settings)


def _normalized_image() -> NormalizedVisualImage:
    return NormalizedVisualImage(
        data=b"\xff\xd8\xffsynthetic-normalized-jpeg\xff\xd9",
        mime_type="image/jpeg",
        width=24,
        height=16,
    )


def _listing_context() -> ListingIn:
    return ListingIn.model_validate(SAFE_LISTING)


def test_visual_inspection_configuration_defaults_to_fully_disabled():
    configured = _visual_settings()

    assert configured.visual_inspection_provider == "disabled"
    assert configured.visual_inspection_model == ""
    assert not hasattr(configured, "visual_inspection_api_key")


@pytest.mark.parametrize(
    ("visual_provider", "visual_model", "openai_api_key"),
    [
        ("disabled", "gpt-4o-mini", "synthetic-unused-key"),
        ("openai", "gpt-4o-mini", ""),
        ("openai", "", "synthetic-unused-key"),
        ("groq", "gpt-4o-mini", "synthetic-unused-key"),
    ],
)
def test_visual_inspection_endpoint_fails_safely_when_unavailable(
    client,
    monkeypatch,
    visual_provider,
    visual_model,
    openai_api_key,
):
    _route_settings(
        monkeypatch,
        visual_inspection_provider=visual_provider,
        visual_inspection_model=visual_model,
        openai_api_key=openai_api_key,
    )
    unexpected_post = _UnexpectedPost()
    monkeypatch.setattr(visual_inspection.httpx, "post", unexpected_post)
    headers = _register_and_login(client)
    analysis = _create_analysis(client, headers)

    response = client.post(
        VISUAL_INSPECTION_PATH.format(analysis_id=analysis["id"]),
        headers=headers,
        files=_photos(1),
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "visual_inspection_unavailable"}
    assert unexpected_post.calls == []


@pytest.mark.parametrize("text_provider", ["mock", "groq", "gpt", "gemini"])
def test_text_provider_does_not_implicitly_enable_visual_inspection(
    monkeypatch,
    text_provider,
):
    unexpected_post = _UnexpectedPost()
    monkeypatch.setattr(visual_inspection.httpx, "post", unexpected_post)
    configured = _visual_settings(
        ai_provider=text_provider,
        visual_inspection_provider="disabled",
        openai_api_key="synthetic-unused-key",
    )

    with pytest.raises(VisualInspectionServiceUnavailable):
        _visual_service(configured)

    assert unexpected_post.calls == []


def test_visual_factory_reuses_openai_key_and_explicit_visual_model(monkeypatch):
    post = _RecordingPost(_OpenAIResponse())
    monkeypatch.setattr(visual_inspection.httpx, "post", post)
    configured = _visual_settings(
        visual_inspection_provider="openai",
        visual_inspection_model="gpt-4o-mini",
        openai_api_key="synthetic-shared-openai-key",
    )

    result = _visual_service(configured).inspect(
        [_normalized_image()],
        _listing_context(),
    )

    assert result == _result()
    assert len(post.calls) == 1
    assert post.calls[0]["headers"]["Authorization"] == (
        "Bearer synthetic-shared-openai-key"
    )
    assert post.calls[0]["json"]["model"] == "gpt-4o-mini"
    assert not hasattr(configured, "visual_inspection_api_key")


def test_visual_factory_passes_explicit_model_override(monkeypatch):
    post = _RecordingPost(_OpenAIResponse())
    monkeypatch.setattr(visual_inspection.httpx, "post", post)
    configured = _visual_settings(
        visual_inspection_provider="openai",
        visual_inspection_model="synthetic-visual-model-override",
        openai_api_key="synthetic-shared-openai-key",
    )

    _visual_service(configured).inspect([_normalized_image()], _listing_context())

    assert post.calls[0]["json"]["model"] == "synthetic-visual-model-override"


def test_configured_openai_visual_endpoint_returns_transient_result(
    client,
    monkeypatch,
):
    _route_settings(
        monkeypatch,
        visual_inspection_provider="openai",
        visual_inspection_model="gpt-4o-mini",
        openai_api_key="synthetic-shared-openai-key",
    )
    accepted = _result()
    post = _RecordingPost(_OpenAIResponse(accepted.model_dump(mode="json")))
    monkeypatch.setattr(visual_inspection.httpx, "post", post)
    headers = _register_and_login(client)
    analysis = _create_analysis(client, headers)
    detail_before = client.get(
        f"/api/analyses/{analysis['id']}",
        headers=headers,
    ).json()
    counts_before = _database_counts()

    response = client.post(
        VISUAL_INSPECTION_PATH.format(analysis_id=analysis["id"]),
        headers=headers,
        files=_photos(1),
    )

    assert response.status_code == 200
    assert response.json() == accepted.model_dump(mode="json")
    assert len(post.calls) == 1
    assert post.calls[0]["json"]["model"] == "gpt-4o-mini"
    assert client.get(
        f"/api/analyses/{analysis['id']}",
        headers=headers,
    ).json() == detail_before
    assert _database_counts() == counts_before


def test_configured_openai_visual_endpoint_maps_provider_failure_safely(
    client,
    monkeypatch,
):
    private_key = "synthetic-private-openai-key"
    private_body = "private-provider-body"
    _route_settings(
        monkeypatch,
        visual_inspection_provider="openai",
        visual_inspection_model="gpt-4o-mini",
        openai_api_key=private_key,
    )
    post = _RecordingPost(
        _OpenAIResponse(status_code=500),
        _OpenAIResponse(status_code=500),
    )
    monkeypatch.setattr(visual_inspection.httpx, "post", post)
    headers = _register_and_login(client)
    analysis = _create_analysis(client, headers)
    counts_before = _database_counts()

    response = client.post(
        VISUAL_INSPECTION_PATH.format(analysis_id=analysis["id"]),
        headers=headers,
        files=_photos(1),
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "visual_inspection_failed"}
    assert len(post.calls) == 2
    assert private_key not in response.text
    assert private_body not in response.text
    assert _database_counts() == counts_before


def test_visual_configuration_does_not_change_text_analysis_contract(
    client,
    monkeypatch,
):
    baseline = _visual_settings(
        ai_provider="mock",
        openai_api_key="synthetic-shared-openai-key",
    )
    configured = _visual_settings(
        ai_provider="mock",
        openai_api_key="synthetic-shared-openai-key",
        visual_inspection_provider="openai",
        visual_inspection_model="synthetic-visual-model-override",
    )
    for setting_name in (
        "ai_provider",
        "openai_model",
        "groq_model",
        "gemini_model",
    ):
        assert getattr(configured, setting_name) == getattr(baseline, setting_name)

    _route_settings(
        monkeypatch,
        visual_inspection_provider="openai",
        visual_inspection_model="synthetic-visual-model-override",
        openai_api_key="synthetic-shared-openai-key",
    )
    headers = _register_and_login(client)

    analysis = _create_analysis(client, headers)

    assert analysis["risk_score"] == 0
    assert analysis["risk_level"] == RiskLevel.low.value


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_visual_inspection_offloads_image_normalization(
    client,
    monkeypatch,
    anyio_backend,
):
    headers = _register_and_login(client)
    analysis = _create_analysis(client, headers)
    provider = _FakeVisualInspectionProvider(_result())
    _install_provider(monkeypatch, provider)
    normalization_started = threading.Event()
    release_normalization = threading.Event()
    counts_before = _database_counts()

    def blocking_normalizer(_source_bytes, _content_type):
        normalization_started.set()
        assert release_normalization.wait(
            timeout=OFFLOAD_REQUEST_TIMEOUT_SECONDS
        )
        return _normalized_image()

    monkeypatch.setattr(routes, "normalize_visual_image", blocking_normalizer)

    visual_response, health_response, health_progressed = (
        await _request_visual_inspection_with_health_probe(
            client,
            headers,
            analysis["id"],
            normalization_started,
            release_normalization,
        )
    )

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert visual_response.status_code == 200
    assert len(provider.calls) == 1
    assert _database_counts() == counts_before
    assert health_progressed == [True]


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_visual_inspection_offloads_provider_execution(
    client,
    monkeypatch,
    anyio_backend,
):
    headers = _register_and_login(client)
    analysis = _create_analysis(client, headers)
    provider_started = threading.Event()
    release_provider = threading.Event()
    counts_before = _database_counts()

    class BlockingProvider:
        def inspect(self, _images, _listing_context):
            provider_started.set()
            assert release_provider.wait(timeout=OFFLOAD_REQUEST_TIMEOUT_SECONDS)
            return _result()

    _install_provider(monkeypatch, BlockingProvider())
    monkeypatch.setattr(
        routes,
        "normalize_visual_image",
        lambda _source_bytes, _content_type: _normalized_image(),
    )

    visual_response, health_response, health_progressed = (
        await _request_visual_inspection_with_health_probe(
            client,
            headers,
            analysis["id"],
            provider_started,
            release_provider,
        )
    )

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert visual_response.status_code == 200
    assert _database_counts() == counts_before
    assert health_progressed == [True]
