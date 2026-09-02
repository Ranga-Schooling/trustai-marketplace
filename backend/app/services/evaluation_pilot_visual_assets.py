"""Fail-closed verification of frozen synthetic pilot visual assets."""

from __future__ import annotations

import binascii
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib
from typing import Any

from app.services.evaluation_contract_identity import load_strict_contract_json


_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_MANIFEST = (
    _ROOT
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "visual-asset-and-truth-records.v1.json"
)
_EXPECTED_SEMANTIC_HASH = (
    "68ffa0e96b740a1bf159aac4e2ebfe559f738d74c7d39cab5d6e778f63eec44b"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TOP_LEVEL_KEYS = {
    "artifact_id",
    "artifact_version",
    "status",
    "classification",
    "purpose",
    "provider_neutral",
    "source_contracts",
    "asset_set",
    "truth_records",
    "privacy",
    "validation_contract",
    "execution_boundary",
    "provider_calls_completed",
    "winner_selected",
    "specification_identity",
}
_TRUTH_KEYS = {
    "fixture_id",
    "asset_set_version",
    "image_order",
    "images",
    "provenance",
    "intentional_modifications",
    "per_photo_visible_regions",
    "known_damage_or_mismatch_regions",
    "canonical_ocr_truth_text",
    "deliberately_unreadable_regions",
    "expected_evidence_relationships",
    "acceptable_observation_variants",
    "forbidden_semantic_conclusions",
    "grading_notes",
}
_IMAGE_KEYS = {
    "photo_number",
    "relative_path",
    "sha256",
    "mime_type",
    "width_pixels",
    "height_pixels",
    "file_size_bytes",
}
_PROVENANCE_KEYS = {
    "synthetic_or_team_owned",
    "creator_or_owner_record",
    "capture_or_construction_method",
    "permission_confirmed",
    "contains_sensitive_data",
}


class PilotVisualAssetError(ValueError):
    """The frozen visual-asset or evaluator-truth boundary was violated."""


def _fail(code: str) -> PilotVisualAssetError:
    return PilotVisualAssetError(code)


@dataclass(frozen=True, slots=True)
class FrozenPilotImage:
    fixture_id: str
    photo_number: int
    path: Path
    sha256: str
    mime_type: str
    width_pixels: int
    height_pixels: int
    file_size_bytes: int


@dataclass(frozen=True, slots=True)
class FrozenPilotVisualAssets:
    artifact_id: str
    artifact_version: str
    semantic_hash: str
    asset_set_version: str
    images: tuple[FrozenPilotImage, ...]
    provider_calls_allowed: bool
    pilot_calls_allowed: bool
    scored_calls_allowed: bool
    provider_calls_completed: int
    winner_selected: bool


def _exact_keys(name: str, value: Any, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise _fail(f"visual_asset_fields:{name}")
    return value


def _nonempty_strings(name: str, value: Any) -> None:
    if (
        type(value) is not list
        or not value
        or any(type(item) is not str or not item for item in value)
    ):
        raise _fail(f"visual_asset_strings:{name}")


def _semantic_hash(raw: dict[str, Any]) -> str:
    detached = json.loads(json.dumps(raw))
    detached["specification_identity"]["semantic_hash"] = None
    canonical = json.dumps(
        detached,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _parse_png(payload: bytes) -> tuple[int, int]:
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise _fail("visual_asset_png_signature")
    offset = 8
    chunks: list[tuple[bytes, bytes]] = []
    while offset < len(payload):
        if len(payload) - offset < 12:
            raise _fail("visual_asset_png_truncated")
        size = struct.unpack(">I", payload[offset : offset + 4])[0]
        kind = payload[offset + 4 : offset + 8]
        end = offset + 12 + size
        if end > len(payload):
            raise _fail("visual_asset_png_truncated")
        data = payload[offset + 8 : offset + 8 + size]
        stored_crc = struct.unpack(">I", payload[offset + 8 + size : end])[0]
        if stored_crc != binascii.crc32(kind + data) & 0xFFFFFFFF:
            raise _fail("visual_asset_png_crc")
        chunks.append((kind, data))
        offset = end
    if offset != len(payload) or [kind for kind, _ in chunks] != [
        b"IHDR",
        b"IDAT",
        b"IEND",
    ]:
        raise _fail("visual_asset_png_chunk_inventory")
    header = chunks[0][1]
    if len(header) != 13:
        raise _fail("visual_asset_png_header")
    width, height, depth, color, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", header
    )
    if (depth, color, compression, filtering, interlace) != (8, 2, 0, 0, 0):
        raise _fail("visual_asset_png_header")
    try:
        raster = zlib.decompress(chunks[1][1])
    except zlib.error as exc:
        raise _fail("visual_asset_png_data") from exc
    row_size = 1 + width * 3
    if len(raster) != height * row_size or any(
        raster[row * row_size] != 0 for row in range(height)
    ):
        raise _fail("visual_asset_png_data")
    return width, height


def _validate_image(
    fixture_id: str,
    raw: Any,
    *,
    asset_root: Path,
) -> FrozenPilotImage:
    image = _exact_keys("image", raw, _IMAGE_KEYS)
    if (
        image["photo_number"] != 1
        or type(image["relative_path"]) is not str
        or image["relative_path"] != f"{fixture_id}/photo-1.png"
        or type(image["sha256"]) is not str
        or _SHA256.fullmatch(image["sha256"]) is None
        or image["mime_type"] != "image/png"
        or type(image["width_pixels"]) is not int
        or type(image["height_pixels"]) is not int
        or type(image["file_size_bytes"]) is not int
        or image["file_size_bytes"] <= 0
    ):
        raise _fail("visual_asset_image_record")
    path = asset_root / image["relative_path"]
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise _fail("visual_asset_missing") from exc
    if len(payload) != image["file_size_bytes"]:
        raise _fail("visual_asset_size")
    if hashlib.sha256(payload).hexdigest() != image["sha256"]:
        raise _fail("visual_asset_hash")
    width, height = _parse_png(payload)
    if (width, height) != (image["width_pixels"], image["height_pixels"]):
        raise _fail("visual_asset_dimensions")
    return FrozenPilotImage(
        fixture_id=fixture_id,
        photo_number=image["photo_number"],
        path=path,
        sha256=image["sha256"],
        mime_type=image["mime_type"],
        width_pixels=width,
        height_pixels=height,
        file_size_bytes=len(payload),
    )


def verify_pilot_visual_assets(
    path: str | Path = _DEFAULT_MANIFEST,
) -> FrozenPilotVisualAssets:
    """Verify exact committed assets, truth structure, privacy, and gate state."""
    path = Path(path)
    try:
        raw = load_strict_contract_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise _fail("visual_asset_manifest_parse") from exc
    raw = _exact_keys("manifest", raw, _TOP_LEVEL_KEYS)
    if (
        raw["artifact_id"] != "visual_asset_and_truth_records_v1"
        or raw["artifact_version"] != "v1"
        or raw["status"] != "frozen_pilot_asset_truth_records"
        or raw["classification"] != "evaluator_only_never_provider_visible"
        or raw["provider_neutral"] is not True
    ):
        raise _fail("visual_asset_manifest_header")
    identity = _exact_keys(
        "identity",
        raw["specification_identity"],
        {"hash_algorithm", "hash_input", "semantic_hash"},
    )
    if (
        identity["hash_algorithm"] != "SHA-256"
        or identity["hash_input"]
        != "canonical_compact_utf8_json_with_semantic_hash_replaced_by_null"
        or identity["semantic_hash"] != _EXPECTED_SEMANTIC_HASH
        or _semantic_hash(raw) != _EXPECTED_SEMANTIC_HASH
    ):
        raise _fail("visual_asset_manifest_identity")

    asset_set = raw["asset_set"]
    if (
        type(asset_set) is not dict
        or asset_set.get("asset_set_version") != "pilot-visual-assets-v1"
        or asset_set.get("asset_root")
        != "docs/testing/ai-evaluation/assets/pilot"
        or asset_set.get("asset_count") != 2
        or asset_set.get("fixture_count") != 2
        or asset_set.get("renderer_path")
        != "backend/tests/reference/pilot_visual_asset_reference.py"
        or type(asset_set.get("renderer_sha256")) is not str
        or _SHA256.fullmatch(asset_set["renderer_sha256"]) is None
        or asset_set.get("external_or_generated_model_content") is not False
        or asset_set.get("third_party_assets") is not False
    ):
        raise _fail("visual_asset_set")
    renderer = _ROOT / asset_set["renderer_path"]
    if hashlib.sha256(renderer.read_bytes()).hexdigest() != asset_set["renderer_sha256"]:
        raise _fail("visual_asset_renderer_hash")

    records = raw["truth_records"]
    if type(records) is not list or len(records) != 2:
        raise _fail("visual_asset_truth_records")
    asset_root = _ROOT / asset_set["asset_root"]
    images: list[FrozenPilotImage] = []
    seen: list[str] = []
    for record_raw in records:
        record = _exact_keys("truth_record", record_raw, _TRUTH_KEYS)
        fixture_id = record["fixture_id"]
        if fixture_id not in {"PV1", "PV2"} or fixture_id in seen:
            raise _fail("visual_asset_fixture_id")
        seen.append(fixture_id)
        if (
            record["asset_set_version"] != asset_set["asset_set_version"]
            or record["image_order"] != [1]
            or type(record["images"]) is not list
            or len(record["images"]) != 1
        ):
            raise _fail("visual_asset_image_order")
        provenance = _exact_keys(
            "provenance", record["provenance"], _PROVENANCE_KEYS
        )
        if (
            provenance["synthetic_or_team_owned"] != "synthetic"
            or provenance["permission_confirmed"] is not True
            or provenance["contains_sensitive_data"] is not False
        ):
            raise _fail("visual_asset_provenance")
        for field in (
            "intentional_modifications",
            "expected_evidence_relationships",
            "acceptable_observation_variants",
            "forbidden_semantic_conclusions",
        ):
            _nonempty_strings(field, record[field])
        for field in (
            "per_photo_visible_regions",
            "known_damage_or_mismatch_regions",
            "canonical_ocr_truth_text",
            "deliberately_unreadable_regions",
        ):
            if type(record[field]) is not list:
                raise _fail(f"visual_asset_truth_type:{field}")
        if type(record["grading_notes"]) is not str or not record["grading_notes"]:
            raise _fail("visual_asset_grading_notes")
        images.append(
            _validate_image(fixture_id, record["images"][0], asset_root=asset_root)
        )
    if seen != ["PV1", "PV2"]:
        raise _fail("visual_asset_fixture_order")

    privacy = raw["privacy"]
    if (
        type(privacy) is not dict
        or privacy.get("personal_information") is not False
        or privacy.get("real_user_listing_data") is not False
        or privacy.get("credentials_or_secrets") is not False
        or privacy.get("current_price_truth") is not False
        or type(privacy.get("evaluator_only_never_provider_visible")) is not list
        or "this artifact" not in privacy["evaluator_only_never_provider_visible"]
    ):
        raise _fail("visual_asset_privacy")
    boundary = raw["execution_boundary"]
    if (
        type(boundary) is not dict
        or boundary.get("execution_state") != "blocked_pre_execution"
        or boundary.get("provider_calls_allowed") is not False
        or boundary.get("pilot_calls_allowed") is not False
        or boundary.get("scored_calls_allowed") is not False
        or boundary.get("this_artifact_independently_authorizes_execution") is not False
        or raw["provider_calls_completed"] != 0
        or raw["winner_selected"] is not False
    ):
        raise _fail("visual_asset_execution_boundary")
    return FrozenPilotVisualAssets(
        artifact_id=raw["artifact_id"],
        artifact_version=raw["artifact_version"],
        semantic_hash=identity["semantic_hash"],
        asset_set_version=asset_set["asset_set_version"],
        images=tuple(images),
        provider_calls_allowed=boundary["provider_calls_allowed"],
        pilot_calls_allowed=boundary["pilot_calls_allowed"],
        scored_calls_allowed=boundary["scored_calls_allowed"],
        provider_calls_completed=raw["provider_calls_completed"],
        winner_selected=raw["winner_selected"],
    )
