"""Server-authoritative, fail-closed application capability tests."""

from types import SimpleNamespace

import pytest

from app.api import routes
from app.services.visual_inspection import (
    VisualInspectionServiceUnavailable,
    get_visual_inspection_service,
    is_visual_inspection_available,
)


def _register_and_login(client) -> dict[str, str]:
    registration = client.post(
        "/api/auth/register",
        json={
            "email": "capability-user@example.com",
            "name": "Capability User",
            "password": "synthetic-password",
        },
    )
    assert registration.status_code == 201

    login = client.post(
        "/api/auth/login",
        json={
            "email": "capability-user@example.com",
            "password": "synthetic-password",
        },
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _settings(
    provider: str,
    api_key: str,
    model: str,
    *,
    text_provider: str = "mock",
):
    return SimpleNamespace(
        ai_provider=text_provider,
        visual_inspection_provider=provider,
        openai_api_key=api_key,
        visual_inspection_model=model,
    )


@pytest.mark.parametrize(
    ("provider", "api_key", "model", "expected"),
    [
        ("", "", "", False),
        ("disabled", "synthetic-key", "synthetic-model", False),
        ("openai", "", "synthetic-model", False),
        ("openai", "synthetic-key", "", False),
        ("unsupported", "synthetic-key", "synthetic-model", False),
        (" OpenAI ", " synthetic-key ", " synthetic-model ", True),
    ],
)
def test_visual_inspection_availability_is_fail_closed_and_matches_service_resolution(
    provider,
    api_key,
    model,
    expected,
):
    configured = _settings(provider, api_key, model)

    assert is_visual_inspection_available(configured) is expected
    if expected:
        service = get_visual_inspection_service(configured)
        assert service is not None
    else:
        with pytest.raises(VisualInspectionServiceUnavailable):
            get_visual_inspection_service(configured)


def test_visual_inspection_availability_is_independent_of_text_provider():
    for text_provider in ("mock", "groq", "gpt", "gemini", "unsupported"):
        configured = _settings(
            "openai",
            "synthetic-key",
            "synthetic-model",
            text_provider=text_provider,
        )

        assert is_visual_inspection_available(configured) is True


def test_capabilities_requires_authentication(client):
    response = client.get("/api/capabilities")

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (_settings("disabled", "", ""), False),
        (_settings("openai", "synthetic-key", "synthetic-model"), True),
        (_settings("openai", "synthetic-key", ""), False),
    ],
)
def test_capabilities_returns_only_the_application_owned_availability_bit(
    client,
    monkeypatch,
    configured,
    expected,
):
    headers = _register_and_login(client)
    monkeypatch.setattr(routes, "settings", configured)

    response = client.get("/api/capabilities", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"visual_inspection_available": expected}
    assert "synthetic-key" not in response.text
    assert "synthetic-model" not in response.text
