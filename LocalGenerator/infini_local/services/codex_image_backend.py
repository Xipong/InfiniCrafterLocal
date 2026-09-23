"""Standalone Codex Images API, using the InfiniCrafter OAuth session only."""
from __future__ import annotations

import base64
import io
import os
from pathlib import Path
import tempfile
import uuid

from infini_local.core.image_dependencies import Image
from infini_local.services import codex_auth

IMAGE_URL = "https://chatgpt.com/backend-api/codex/images/generations"
MAX_IMAGE_BYTES = 32 * 1024 * 1024


def generate_image(prompt: str, negative: str, output_path: Path, *, model: str, quality: str, size: str, timeout: int) -> None:
    if not isinstance(prompt, str) or not prompt.strip():
        raise codex_auth.CodexError("Codex image generation requires an authored prompt")
    if not model.strip() or quality not in {"low", "medium", "high", "auto"} or size not in {"1024x1024", "1536x1024", "1024x1536", "auto"}:
        raise codex_auth.CodexError("Invalid Codex image model, quality or size configuration")
    if Image is None:
        raise codex_auth.CodexError("Pillow is required to validate Codex PNG output")
    credentials = codex_auth.get_credentials()
    # No host LLM rewrites the Visual Director's prompt. The API has no separate
    # negative-prompt parameter; preserve that authored text in a labelled suffix.
    full_prompt = prompt + ("\n\nAvoid: " + negative if negative else "")
    response = codex_auth.post_json(IMAGE_URL, {
        "model": model, "prompt": full_prompt, "n": 1, "quality": quality,
        "size": size, "background": "opaque",
    }, headers={
        "Authorization": "Bearer " + credentials.access_token,
        "ChatGPT-Account-Id": credentials.account_id,
        "originator": "infinicrafter",
        "x-codex-image-turn-id": str(uuid.uuid4()),
    }, timeout=timeout, limit=48 * 1024 * 1024)
    data = response.get("data")
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict) or not isinstance(data[0].get("b64_json"), str):
        raise codex_auth.CodexError("Codex response must contain exactly one base64 image")
    try:
        raw = base64.b64decode(data[0]["b64_json"], validate=True)
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("image byte limit")
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != "PNG" or max(image.size) > 4096 or min(image.size) < 1:
                raise ValueError("image format or dimensions")
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
    except Exception:
        raise codex_auth.CodexError("Codex returned invalid or oversized PNG data") from None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".codex-image-", dir=output_path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
        os.replace(temporary, output_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
