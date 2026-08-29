"""Request-scoped Visual Inspection image-normalization boundary tests."""

from io import BytesIO

import pytest
from PIL import Image

from app.services.visual_inspection_images import (
    VisualImageValidationError,
    normalize_visual_image,
)


MIB = 1024 * 1024
MAX_SOURCE_BYTES = 4 * MIB
MAX_SOURCE_DIMENSION = 8_000
MAX_DECODED_PIXELS = 25_000_000
MAX_NORMALIZED_EDGE = 1_600


def _image_bytes(
    image_format: str,
    *,
    mode: str = "RGB",
    size: tuple[int, int] = (24, 16),
    color=(32, 96, 160),
    **save_options,
) -> bytes:
    image = Image.new(mode, size, color)
    output = BytesIO()
    image.save(output, format=image_format, **save_options)
    return output.getvalue()


def _open_normalized(result):
    assert result.mime_type == "image/jpeg"
    assert isinstance(result.data, bytes)
    assert result.data

    image = Image.open(BytesIO(result.data))
    image.load()
    assert image.format == "JPEG"
    assert image.mode == "RGB"
    assert result.width == image.width
    assert result.height == image.height
    return image


def _assert_error_code(source_bytes: bytes, declared_mime_type: str, code: str):
    with pytest.raises(VisualImageValidationError) as exc_info:
        normalize_visual_image(source_bytes, declared_mime_type)

    assert code in exc_info.value.codes
    return exc_info.value


def test_normalizer_accepts_valid_jpeg_and_returns_jpeg():
    result = normalize_visual_image(_image_bytes("JPEG"), "image/jpeg")

    output = _open_normalized(result)
    assert output.size == (24, 16)


def test_normalizer_accepts_valid_png_and_returns_jpeg():
    result = normalize_visual_image(_image_bytes("PNG"), "image/png")

    output = _open_normalized(result)
    assert output.size == (24, 16)


def test_normalizer_accepts_single_frame_webp_and_returns_jpeg():
    result = normalize_visual_image(_image_bytes("WEBP"), "image/webp")

    output = _open_normalized(result)
    assert output.size == (24, 16)


@pytest.mark.parametrize(
    ("source_bytes", "declared_mime_type"),
    [
        (_image_bytes("JPEG"), "image/png"),
        (_image_bytes("PNG"), "image/jpeg"),
    ],
)
def test_normalizer_rejects_declared_mime_and_decoded_format_mismatch(
    source_bytes,
    declared_mime_type,
):
    _assert_error_code(source_bytes, declared_mime_type, "format_mismatch")


@pytest.mark.parametrize(
    ("source_bytes", "declared_mime_type"),
    [
        (_image_bytes("GIF"), "image/gif"),
        (b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', "image/svg+xml"),
        (b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1", "image/heic"),
        (_image_bytes("TIFF"), "image/tiff"),
        (b"%PDF-1.7\n% synthetic\n", "application/pdf"),
        (_image_bytes("JPEG"), "application/octet-stream"),
    ],
)
def test_normalizer_rejects_unsupported_types(source_bytes, declared_mime_type):
    _assert_error_code(source_bytes, declared_mime_type, "unsupported_type")


@pytest.mark.parametrize(
    "source_bytes",
    [
        b"not an image",
        b"\xff\xd8\xff\xe0\x00\x10JFIF",
    ],
)
def test_normalizer_rejects_corrupt_or_truncated_image_data(source_bytes):
    _assert_error_code(source_bytes, "image/jpeg", "invalid_image")


def test_normalizer_rejects_source_over_per_image_byte_limit_before_decode(monkeypatch):
    def fail_if_decoding_is_attempted(*_args, **_kwargs):
        raise AssertionError("oversized source reached the image decoder")

    monkeypatch.setattr(Image, "open", fail_if_decoding_is_attempted)
    source_bytes = b"x" * (MAX_SOURCE_BYTES + 1)

    _assert_error_code(source_bytes, "image/jpeg", "image_too_large")


class _MetadataOnlyImage:
    format = "JPEG"
    n_frames = 1
    is_animated = False

    def __init__(self, size: tuple[int, int]):
        self.size = size

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def load(self):
        raise AssertionError("unsafe image pixels were decoded")


def test_normalizer_rejects_source_dimension_over_8000_before_pixel_decode(monkeypatch):
    monkeypatch.setattr(
        Image,
        "open",
        lambda *_args, **_kwargs: _MetadataOnlyImage((MAX_SOURCE_DIMENSION + 1, 1)),
    )

    _assert_error_code(b"synthetic metadata fixture", "image/jpeg", "dimensions_too_large")


def test_normalizer_rejects_more_than_25_megapixels_before_pixel_decode(monkeypatch):
    width = 5_001
    height = 5_000
    assert width * height > MAX_DECODED_PIXELS
    assert max(width, height) <= MAX_SOURCE_DIMENSION
    monkeypatch.setattr(
        Image,
        "open",
        lambda *_args, **_kwargs: _MetadataOnlyImage((width, height)),
    )

    _assert_error_code(b"synthetic metadata fixture", "image/jpeg", "too_many_pixels")


def test_normalizer_rejects_animated_webp():
    frames = [
        Image.new("RGB", (12, 12), (255, 0, 0)),
        Image.new("RGB", (12, 12), (0, 0, 255)),
    ]
    output = BytesIO()
    frames[0].save(
        output,
        format="WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
    )

    _assert_error_code(output.getvalue(), "image/webp", "animated_image")


def test_normalizer_applies_exif_orientation():
    exif = Image.Exif()
    exif[274] = 6
    source_bytes = _image_bytes(
        "JPEG",
        size=(30, 10),
        exif=exif,
    )

    result = normalize_visual_image(source_bytes, "image/jpeg")

    output = _open_normalized(result)
    assert output.size == (10, 30)


def test_normalizer_strips_exif_icc_and_comment_metadata():
    exif = Image.Exif()
    exif[270] = "harmless synthetic description"
    exif[315] = "synthetic author"
    source_bytes = _image_bytes(
        "JPEG",
        exif=exif,
        icc_profile=b"synthetic-icc-profile",
        comment=b"synthetic comment",
    )

    result = normalize_visual_image(source_bytes, "image/jpeg")

    output = _open_normalized(result)
    assert not output.getexif()
    assert "exif" not in output.info
    assert "icc_profile" not in output.info
    assert "comment" not in output.info


def test_normalizer_resizes_longest_edge_and_preserves_aspect_ratio():
    source_bytes = _image_bytes("JPEG", size=(2_000, 1_000))

    result = normalize_visual_image(source_bytes, "image/jpeg")

    output = _open_normalized(result)
    assert output.size == (MAX_NORMALIZED_EDGE, 800)
    assert max(output.size) <= MAX_NORMALIZED_EDGE


def test_normalizer_flattens_alpha_safely_to_rgb_jpeg():
    source_bytes = _image_bytes(
        "PNG",
        mode="RGBA",
        size=(20, 10),
        color=(255, 0, 0, 0),
    )

    result = normalize_visual_image(source_bytes, "image/png")

    output = _open_normalized(result)
    red, green, blue = output.getpixel((10, 5))
    assert min(red, green, blue) >= 240


def test_validation_error_exposes_only_safe_codes():
    private_marker = "camera-owner=synthetic-private-marker"
    source_bytes = private_marker.encode()

    error = _assert_error_code(source_bytes, "image/jpeg", "invalid_image")

    assert error.codes == ("invalid_image",)
    assert private_marker not in str(error)
    assert private_marker not in repr(error)
    assert source_bytes not in error.args
