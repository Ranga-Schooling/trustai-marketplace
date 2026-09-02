"""Pure validation and normalization for request-scoped visual images."""

import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_SOURCE_DIMENSION = 8_000
MAX_DECODED_PIXELS = 25_000_000
MAX_NORMALIZED_EDGE = 1_600

_MIME_FORMATS = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
_ALLOWED_FORMATS = tuple(_MIME_FORMATS.values())


@dataclass(frozen=True, slots=True)
class NormalizedVisualImage:
    data: bytes
    mime_type: str
    width: int
    height: int


class VisualImageValidationError(ValueError):
    """Image rejection containing only an application-owned safe code."""

    def __init__(self, code: str) -> None:
        self.codes = (code,)
        super().__init__(f"Visual image validation failed: {code}")


def _reject(code: str) -> None:
    raise VisualImageValidationError(code)


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    if "A" in image.getbands() or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, rgba).convert("RGB")
    return image.convert("RGB")


def normalize_visual_image(
    source_bytes: bytes,
    declared_mime_type: str,
) -> NormalizedVisualImage:
    """Validate one source image and return a metadata-free RGB JPEG."""

    if not isinstance(source_bytes, bytes) or not source_bytes:
        _reject("invalid_image")
    if len(source_bytes) > MAX_SOURCE_BYTES:
        _reject("image_too_large")

    expected_format = _MIME_FORMATS.get(declared_mime_type)
    if expected_format is None:
        _reject("unsupported_type")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)

            with Image.open(BytesIO(source_bytes), formats=_ALLOWED_FORMATS) as image:
                if image.format != expected_format:
                    _reject("format_mismatch")

                width, height = image.size
                if width > MAX_SOURCE_DIMENSION or height > MAX_SOURCE_DIMENSION:
                    _reject("dimensions_too_large")
                if width * height > MAX_DECODED_PIXELS:
                    _reject("too_many_pixels")
                if getattr(image, "n_frames", 1) > 1 or getattr(
                    image, "is_animated", False
                ):
                    _reject("animated_image")

                image.load()
                oriented = ImageOps.exif_transpose(image)

            if max(oriented.size) > MAX_NORMALIZED_EDGE:
                oriented.thumbnail(
                    (MAX_NORMALIZED_EDGE, MAX_NORMALIZED_EDGE),
                    Image.Resampling.LANCZOS,
                )

            normalized = _flatten_to_rgb(oriented)
            normalized.info.clear()
            output = BytesIO()
            normalized.save(output, format="JPEG", quality=90)
            normalized_bytes = output.getvalue()

            with Image.open(BytesIO(normalized_bytes), formats=("JPEG",)) as result:
                result.load()
                if result.format != "JPEG" or result.mode != "RGB":
                    _reject("invalid_image")
                final_width, final_height = result.size

    except VisualImageValidationError:
        raise
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        EOFError,
        OSError,
        SyntaxError,
        ValueError,
    ):
        raise VisualImageValidationError("invalid_image") from None

    return NormalizedVisualImage(
        data=normalized_bytes,
        mime_type="image/jpeg",
        width=final_width,
        height=final_height,
    )
