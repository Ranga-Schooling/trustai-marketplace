"""OpenAI-backed Visual Inspection service contract tests."""

import base64
import json

import httpx
import pytest

from app.schemas.schemas import ListingIn
from app.services import visual_inspection
from app.services.visual_inspection import (
    VisualInspectionResult,
    VisualInspectionServiceFailure,
)
from app.services.visual_inspection_images import NormalizedVisualImage


OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
MODEL_NAME = "gpt-4o-mini"
SYNTHETIC_API_KEY = "synthetic-openai-test-key"
PRIVATE_PROVIDER_BODY = "private-provider-response-marker"
PRIVATE_LISTING_URL = "https://private.example.invalid/do-not-send-this-url"

VALID_RESULT = {
    "findings": [
        {
            "category": "visible_damage",
            "observation": "Photo 1 visibly shows a scratch on the upper-right corner.",
            "photo_numbers": [1],
        }
    ]
}

POLICY_INVALID_RESULT = {
    "findings": [
        {
            "category": "visible_detail",
            "observation": "The photographed item is definitely counterfeit.",
            "photo_numbers": [1],
        }
    ]
}


class FakeOpenAIResponse:
    def __init__(
        self,
        content: str = json.dumps(VALID_RESULT),
        *,
        status_code: int = 200,
        error_body: str = PRIVATE_PROVIDER_BODY,
    ) -> None:
        self.content = content
        self._response = httpx.Response(
            status_code,
            request=httpx.Request("POST", OPENAI_ENDPOINT),
            json={"error": {"message": error_body}},
        )

    def raise_for_status(self) -> None:
        self._response.raise_for_status()

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": self.content,
                    }
                }
            ]
        }


class RecordingPost:
    def __init__(self, *outcomes) -> None:
        self.outcomes = iter(outcomes)
        self.calls: list[dict] = []

    def __call__(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        outcome = next(self.outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _listing(*, url: str = "https://example.com/listing/visual-test") -> ListingIn:
    return ListingIn(
        title="Samsung Galaxy S22, lightly used",
        price=35.0,
        currency="USD",
        source="OLX",
        description="Works perfectly, with minor scratches on the back.",
        url=url,
    )


def _image(number: int) -> NormalizedVisualImage:
    return NormalizedVisualImage(
        data=b"\xff\xd8\xff" + bytes([number]) + b"\xff\xd9",
        mime_type="image/jpeg",
        width=24,
        height=16,
    )


def _service(post: RecordingPost):
    service_class = getattr(
        visual_inspection,
        "OpenAIVisualInspectionService",
    )
    return service_class(
        api_key=SYNTHETIC_API_KEY,
        model_name=MODEL_NAME,
        post=post,
    )


def _payload(post: RecordingPost, call: int = 0) -> dict:
    return post.calls[call]["json"]


def _system_instruction(payload: dict) -> str:
    messages = payload["messages"]
    system_messages = [message for message in messages if message["role"] == "system"]
    return "\n".join(str(message["content"]) for message in system_messages)


def _user_parts(payload: dict) -> list[dict]:
    return next(
        message["content"]
        for message in payload["messages"]
        if message["role"] == "user"
    )


def _image_parts(payload: dict) -> list[dict]:
    return [part for part in _user_parts(payload) if part["type"] == "image_url"]


def _listing_text(payload: dict) -> str:
    return next(part["text"] for part in _user_parts(payload) if part["type"] == "text")


def _assert_safe_failure(
    exc_info,
    *private_values: str,
) -> None:
    assert isinstance(exc_info.value, VisualInspectionServiceFailure)
    rendered = f"{exc_info.value!s} {exc_info.value!r} {exc_info.value.args!r}"
    for private_value in private_values:
        assert private_value not in rendered


def test_openai_visual_request_uses_expected_endpoint_model_and_options():
    post = RecordingPost(FakeOpenAIResponse())

    _service(post).inspect([_image(1)], _listing())

    assert len(post.calls) == 1
    call = post.calls[0]
    payload = call["json"]
    assert call["url"] == OPENAI_ENDPOINT
    assert call["headers"] == {
        "Authorization": f"Bearer {SYNTHETIC_API_KEY}",
        "Content-Type": "application/json",
    }
    assert call["timeout"] > 0
    assert payload["model"] == MODEL_NAME
    assert payload["store"] is False
    assert 0 <= payload["temperature"] <= 0.2
    assert "tools" not in payload
    assert "tool_choice" not in payload
    assert "web_search" not in json.dumps(payload).casefold()


def test_openai_visual_request_sends_one_normalized_jpeg_at_high_detail():
    image = _image(1)
    post = RecordingPost(FakeOpenAIResponse())

    _service(post).inspect([image], _listing())

    parts = _image_parts(_payload(post))
    assert parts == [
        {
            "type": "image_url",
            "image_url": {
                "url": "data:image/jpeg;base64," + base64.b64encode(image.data).decode(),
                "detail": "high",
            },
        }
    ]


def test_openai_visual_request_preserves_three_image_order():
    images = [_image(1), _image(2), _image(3)]
    post = RecordingPost(FakeOpenAIResponse())

    _service(post).inspect(images, _listing())

    parts = _image_parts(_payload(post))
    assert len(parts) == 3
    assert [part["image_url"]["url"] for part in parts] == [
        "data:image/jpeg;base64," + base64.b64encode(image.data).decode()
        for image in images
    ]
    assert all(part["image_url"]["detail"] == "high" for part in parts)


def test_openai_visual_request_contains_only_bounded_listing_and_image_context():
    post = RecordingPost(FakeOpenAIResponse())

    _service(post).inspect([_image(1)], _listing(url=PRIVATE_LISTING_URL))

    payload = _payload(post)
    listing_text = _listing_text(payload)
    for expected in (
        "Samsung Galaxy S22, lightly used",
        "Works perfectly, with minor scratches on the back.",
        "OLX",
        "35",
        "USD",
    ):
        assert expected in listing_text

    serialized = json.dumps(payload).casefold()
    assert PRIVATE_LISTING_URL.casefold() not in serialized
    assert "email" not in serialized
    assert "password" not in serialized
    assert "user_id" not in serialized
    assert "analysis_id" not in serialized
    assert "filename" not in serialized
    assert "exif" not in serialized
    assert "local path" not in serialized
    assert "image/png" not in serialized
    for part in _image_parts(payload):
        assert set(part) == {"type", "image_url"}
        assert set(part["image_url"]) == {"url", "detail"}


def test_openai_visual_requests_cap_initial_and_corrective_output_tokens():
    post = RecordingPost(
        FakeOpenAIResponse(json.dumps(POLICY_INVALID_RESULT)),
        FakeOpenAIResponse(),
    )

    _service(post).inspect([_image(1)], _listing())

    assert len(post.calls) == 2
    assert [
        _payload(post, call)["max_completion_tokens"]
        for call in range(len(post.calls))
    ] == [2048, 2048]


def test_openai_visual_system_instruction_pins_evidence_boundaries():
    post = RecordingPost(FakeOpenAIResponse())

    _service(post).inspect([_image(1)], _listing())

    instruction = _system_instruction(_payload(post)).casefold()
    assert "supplied photo" in instruction
    assert "listing" in instruction and "context" in instruction
    assert "visible" in instruction
    assert "uncertain" in instruction or "uncertainty" in instruction
    assert "authentic" in instruction or "counterfeit" in instruction
    assert "ownership" in instruction or "stolen" in instruction
    assert "identity" in instruction or "demographic" in instruction
    assert "internal" in instruction or "hidden" in instruction
    assert "market" in instruction and "price" in instruction
    assert "text" in instruction and "instruction" in instruction
    assert "structured" in instruction or "json" in instruction


def test_openai_visual_request_uses_strict_existing_result_schema():
    post = RecordingPost(FakeOpenAIResponse())

    _service(post).inspect([_image(1)], _listing())

    response_format = _payload(post)["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"findings"}
    finding_schema = schema["$defs"]["VisualInspectionFinding"]
    assert finding_schema["additionalProperties"] is False
    serialized_schema = json.dumps(schema).casefold()
    for forbidden_field in (
        "risk_score",
        "risk_level",
        "recommendation",
        "price_plausibility",
        "raw_response",
    ):
        assert forbidden_field not in serialized_schema


def test_openai_visual_service_returns_validated_result_without_raw_response():
    post = RecordingPost(FakeOpenAIResponse())

    result = _service(post).inspect([_image(1)], _listing())

    assert isinstance(result, VisualInspectionResult)
    assert result.model_dump(mode="json") == VALID_RESULT
    assert set(result.model_dump()) == {"findings"}
    assert not hasattr(result, "raw_response")
    assert len(post.calls) == 1


@pytest.mark.parametrize(
    "invalid_content",
    [
        "not valid JSON",
        json.dumps({"observations": []}),
        json.dumps({**VALID_RESULT, "risk_score": 80}),
        json.dumps(
            {
                "findings": [
                    {
                        "category": "visible_detail",
                        "observation": "A visible label is present.",
                        "photo_numbers": [4],
                    }
                ]
            }
        ),
    ],
)
def test_openai_visual_schema_failures_retry_once_then_fail_safely(invalid_content):
    post = RecordingPost(
        FakeOpenAIResponse(invalid_content),
        FakeOpenAIResponse(invalid_content),
    )

    with pytest.raises(VisualInspectionServiceFailure) as exc_info:
        _service(post).inspect([_image(1)], _listing())

    assert len(post.calls) == 2
    _assert_safe_failure(exc_info, invalid_content, SYNTHETIC_API_KEY)


def test_openai_visual_schema_failure_retries_then_returns_compliant_result():
    rejected_content = json.dumps({"observations": []})
    post = RecordingPost(
        FakeOpenAIResponse(rejected_content),
        FakeOpenAIResponse(),
    )

    result = _service(post).inspect([_image(1)], _listing())

    assert result.model_dump(mode="json") == VALID_RESULT
    assert len(post.calls) == 2
    correction = json.dumps(_payload(post, 1)).casefold()
    assert "invalid_visual_schema" in correction
    assert "correct" in correction or "rejected" in correction
    assert rejected_content.casefold() not in correction


@pytest.mark.parametrize("status_code", [401, 403, 429, 500])
def test_openai_visual_http_failures_retry_once_then_fail_safely(status_code):
    post = RecordingPost(
        FakeOpenAIResponse(status_code=status_code),
        FakeOpenAIResponse(status_code=status_code),
    )

    with pytest.raises(VisualInspectionServiceFailure) as exc_info:
        _service(post).inspect([_image(1)], _listing())

    assert len(post.calls) == 2
    _assert_safe_failure(exc_info, PRIVATE_PROVIDER_BODY, SYNTHETIC_API_KEY)


@pytest.mark.parametrize("error_class", [httpx.ReadTimeout, httpx.ConnectError])
def test_openai_visual_network_failures_retry_once_then_fail_safely(error_class):
    private_error = "private-network-error-marker"
    request = httpx.Request("POST", OPENAI_ENDPOINT)
    post = RecordingPost(
        error_class(private_error, request=request),
        error_class(private_error, request=request),
    )

    with pytest.raises(VisualInspectionServiceFailure) as exc_info:
        _service(post).inspect([_image(1)], _listing())

    assert len(post.calls) == 2
    _assert_safe_failure(exc_info, private_error, SYNTHETIC_API_KEY)


def test_openai_visual_policy_violation_retries_with_safe_corrective_context():
    offending_prose = POLICY_INVALID_RESULT["findings"][0]["observation"]
    images = [_image(1), _image(2)]
    post = RecordingPost(
        FakeOpenAIResponse(json.dumps(POLICY_INVALID_RESULT)),
        FakeOpenAIResponse(),
    )

    result = _service(post).inspect(images, _listing())

    assert result.model_dump(mode="json") == VALID_RESULT
    assert len(post.calls) == 2
    first_payload = _payload(post, 0)
    second_payload = _payload(post, 1)
    correction = json.dumps(second_payload).casefold()
    assert "authenticity_claim" in correction
    assert "correct" in correction or "rejected" in correction
    assert offending_prose.casefold() not in correction
    assert _listing_text(second_payload) == _listing_text(first_payload)
    assert [part["image_url"] for part in _image_parts(second_payload)] == [
        part["image_url"] for part in _image_parts(first_payload)
    ]


def test_openai_visual_two_policy_violations_fail_closed_without_prose():
    offending_prose = POLICY_INVALID_RESULT["findings"][0]["observation"]
    post = RecordingPost(
        FakeOpenAIResponse(json.dumps(POLICY_INVALID_RESULT)),
        FakeOpenAIResponse(json.dumps(POLICY_INVALID_RESULT)),
    )

    with pytest.raises(VisualInspectionServiceFailure) as exc_info:
        _service(post).inspect([_image(1)], _listing())

    assert len(post.calls) == 2
    _assert_safe_failure(exc_info, offending_prose, SYNTHETIC_API_KEY)


def test_openai_visual_service_leaves_actual_upload_count_to_endpoint():
    globally_valid_photo_three = {
        "findings": [
            {
                "category": "visible_text",
                "observation": "Photo 3 visibly shows a printed model label.",
                "photo_numbers": [3],
            }
        ]
    }
    post = RecordingPost(
        FakeOpenAIResponse(json.dumps(globally_valid_photo_three)),
    )

    result = _service(post).inspect([_image(1)], _listing())

    assert result.findings[0].photo_numbers == [3]
    assert len(post.calls) == 1
