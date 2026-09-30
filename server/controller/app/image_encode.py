"""Derive a model-sized image from a full-resolution screenshot.

The full PNG stays on disk for the human live view. What an agent receives is a smaller,
capped derivative so a screenshot costs hundreds of tokens, not thousands.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Literal

from PIL import Image

ImageFormat = Literal["jpeg", "png"]

# Encoded (base64) size ceiling. About 400 KB of base64 is roughly 300 KB of image bytes.
MAX_BASE64_BYTES = 400_000
MIN_SCALE = 0.1
MIN_QUALITY = 30
_MAX_ATTEMPTS = 12

MIME = {"jpeg": "image/jpeg", "png": "image/png"}


@dataclass(frozen=True)
class EncodedImage:
    data: str  # base64
    mime: str
    format: str
    width: int
    height: int
    source_width: int
    source_height: int
    scale: float
    quality: int | None
    raw_bytes: int
    capped: bool

    @property
    def size_kb(self) -> int:
        return max(1, round(self.raw_bytes / 1024))

    def placeholder(self) -> str:
        return f"[image {self.size_kb} KB {self.format}]"


def _encode(image: Image.Image, fmt: str, quality: int) -> bytes:
    buffer = io.BytesIO()
    if fmt == "jpeg":
        image.convert("RGB").save(buffer, format="JPEG", quality=quality, optimize=True)
    else:
        image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def encode_for_model(
    png_bytes: bytes,
    *,
    fmt: str = "jpeg",
    scale: float = 0.75,
    quality: int = 60,
    max_base64_bytes: int = MAX_BASE64_BYTES,
) -> EncodedImage:
    """Downscale and encode. If the base64 form exceeds the cap, quality then scale are reduced."""
    fmt = "png" if fmt == "png" else "jpeg"
    scale = min(1.0, max(MIN_SCALE, float(scale)))
    quality = min(95, max(MIN_QUALITY, int(quality)))
    with Image.open(io.BytesIO(png_bytes)) as source:
        source.load()
        src_w, src_h = source.size
        current_scale = scale
        current_quality = quality
        capped = False
        for _ in range(_MAX_ATTEMPTS):
            width = max(1, round(src_w * current_scale))
            height = max(1, round(src_h * current_scale))
            resized = source if (width, height) == (src_w, src_h) else source.resize((width, height), Image.LANCZOS)
            raw = _encode(resized, fmt, current_quality)
            if len(raw) * 4 // 3 + 4 <= max_base64_bytes:
                break
            capped = True
            if fmt == "jpeg" and current_quality > MIN_QUALITY:
                current_quality = max(MIN_QUALITY, current_quality - 15)
            else:
                current_scale = max(MIN_SCALE, current_scale * 0.8)
        # If every attempt was over the cap the last (smallest) encoding is returned; the
        # caller reports `capped`.
    return EncodedImage(
        data=base64.b64encode(raw).decode("ascii"),
        mime=MIME[fmt],
        format=fmt,
        width=width,
        height=height,
        source_width=src_w,
        source_height=src_h,
        scale=round(current_scale, 3),
        quality=current_quality if fmt == "jpeg" else None,
        raw_bytes=len(raw),
        capped=capped,
    )
