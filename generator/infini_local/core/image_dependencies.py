from __future__ import annotations


try:
    from PIL import Image, ImageDraw, ImageFilter

    PILLOW_IMPORT_ERROR = ""
except Exception as pillow_error:  # pragma: no cover - exercised on minimal installs
    # Keep non-visual tooling importable; visual startup validates this dependency.
    Image = None
    ImageDraw = None
    ImageFilter = None
    PILLOW_IMPORT_ERROR = repr(pillow_error)


__all__ = ["Image", "ImageDraw", "ImageFilter", "PILLOW_IMPORT_ERROR"]
