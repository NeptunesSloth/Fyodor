"""Validate uploaded images by their actual content (never the file name or declared type).

Only PNG, JPEG and WEBP are accepted. We read the real format from the magic bytes and the
dimensions from the image header, without decoding pixels or running any external code.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

MAX_BYTES = 20 * 1024 * 1024
MAX_SIDE = 8192
MIME = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}


class InvalidImage(ValueError):
    pass


@dataclass(frozen=True)
class ImageInfo:
    format: str  # png | jpeg | webp
    width: int
    height: int

    @property
    def mime(self) -> str:
        return MIME[self.format]


def sniff(data: bytes) -> ImageInfo:
    if len(data) > MAX_BYTES:
        raise InvalidImage(f"Image is too large ({len(data) // 1024 // 1024} MB; max {MAX_BYTES // 1024 // 1024} MB)")
    if len(data) < 16:
        raise InvalidImage("Not an image")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        info = _png(data)
    elif data.startswith(b"\xff\xd8\xff"):
        info = _jpeg(data)
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        info = _webp(data)
    else:
        raise InvalidImage("Only PNG, JPEG and WEBP images are accepted")
    if not (0 < info.width <= MAX_SIDE and 0 < info.height <= MAX_SIDE):
        raise InvalidImage(f"Image is {info.width}×{info.height}; the limit is {MAX_SIDE}×{MAX_SIDE}")
    return info


def _png(data: bytes) -> ImageInfo:
    if data[12:16] != b"IHDR" or len(data) < 24:
        raise InvalidImage("Damaged PNG")
    width, height = struct.unpack(">II", data[16:24])
    return ImageInfo("png", width, height)


def _jpeg(data: bytes) -> ImageInfo:
    i = 2
    n = len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            raise InvalidImage("Damaged JPEG")
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # no length
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2 : i + 4])[0]
        if length < 2:
            raise InvalidImage("Damaged JPEG")
        # SOF0..SOF15 except DHT(C4), JPG(C8), DAC(CC) carry the frame size
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if i + 9 > n:
                break
            height, width = struct.unpack(">HH", data[i + 5 : i + 9])
            return ImageInfo("jpeg", width, height)
        if marker == 0xDA:  # start of scan before any frame header
            break
        i += 2 + length
    raise InvalidImage("Damaged JPEG (no frame header)")


def _webp(data: bytes) -> ImageInfo:
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return ImageInfo("webp", width, height)
    if chunk == b"VP8 " and len(data) >= 30:
        if data[23:26] != b"\x9d\x01\x2a":
            raise InvalidImage("Damaged WEBP")
        width, height = struct.unpack("<HH", data[26:30])
        return ImageInfo("webp", width & 0x3FFF, height & 0x3FFF)
    if chunk == b"VP8L" and len(data) >= 25:
        if data[20] != 0x2F:
            raise InvalidImage("Damaged WEBP")
        bits = int.from_bytes(data[21:25], "little")
        return ImageInfo("webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
    raise InvalidImage("Damaged or unsupported WEBP")
