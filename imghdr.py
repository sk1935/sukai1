"""Compatibility implementation of the deprecated stdlib imghdr module for Python 3.13.

This minimal version provides imghdr.what() for libraries that still import
imghdr (e.g., python-telegram-bot 13.x). The implementation is adapted from the
CPython 3.12 standard library (PSF license)."""
from __future__ import annotations

import struct
from typing import BinaryIO, Iterable, Optional

__all__ = ["what"]

def _read_file(h: Optional[bytes], file: BinaryIO) -> bytes:
    if h is None:
        h = file.read(32)
    return h


def what(file, h=None):
    """Detect image type.

    file can be a file path or file-like object. This replicates the behaviour
    expected by legacy callers of the stdlib imghdr module.
    """
    if hasattr(file, "read"):
        h = _read_file(h, file)  # type: ignore[arg-type]
    else:
        with open(file, "rb") as fp:
            h = _read_file(h, fp)

    if len(h) < 4:
        return None

    tests = [test_jpeg, test_png, test_gif, test_tiff, test_bmp, test_webp]
    for test in tests:
        res = test(h)
        if res:
            return res
    return None


def test_jpeg(h: bytes) -> Optional[str]:
    if h[:3] == b"\xff\xd8\xff":
        return "jpeg"
    return None


def test_png(h: bytes) -> Optional[str]:
    if h[:8] == b"\211PNG\r\n\032\n":
        return "png"
    return None


def test_gif(h: bytes) -> Optional[str]:
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def test_bmp(h: bytes) -> Optional[str]:
    if h[:2] == b"BM":
        return "bmp"
    return None


def test_tiff(h: bytes) -> Optional[str]:
    if h[:4] in (b"MM\x00*", b"II*\x00"):
        return "tiff"
    return None


def test_webp(h: bytes) -> Optional[str]:
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return "webp"
    return None
