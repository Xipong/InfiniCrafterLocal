from __future__ import annotations

import re
from pathlib import Path
from typing import Any


class ImageOutputIOError(OSError):
    """An actual local image-output filesystem operation failed, not decoding."""



def write_image_bytes(path: Path, raw: bytes) -> None:
    """Keep disk errors distinct from transport/base64/provider content errors."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    except OSError as exc:
        raise ImageOutputIOError("image bytes write failed") from exc


def save_image_output(image: Any, path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata = image.info.get("infini.chroma-key")
        if metadata is not None:
            from PIL.PngImagePlugin import PngInfo
            info = PngInfo()
            info.add_text("infini.chroma-key", metadata)
            image.save(path, pnginfo=info)
        else:
            image.save(path)
    except OSError as exc:
        raise ImageOutputIOError("processed image write failed") from exc


def load_image_input(path: str, image_cls: Any) -> Any:
    try:
        with image_cls.open(path) as source:
            return source.convert("RGBA")
    except OSError as exc:
        # UnidentifiedImageError and Pillow's truncated-image OSError have no
        # filesystem errno. They remain bounded technical-quality failures.
        if exc.errno is not None:
            raise ImageOutputIOError("image input filesystem read failed") from exc
        raise


def strip_sprite_resolution_tokens(text: str) -> str:
    """Remove final sprite-size instructions from prompts sent to image models.

    The generator renders a large canvas and the pipeline crops/downscales later;
    telling Z-Image that the subject is "16x16" or "32x32 resolution" fights the
    fill/crop contract and produces tiny blobs.  Keep pixel-art style, drop size.
    """
    t = str(text or "")
    t = re.sub(r"(?i)\b\d{1,3}\s*[x×]\s*\d{1,3}\s*(?:px|pixel[- ]art|pixel(?:s)?|resolution|sprite|icon)?\b", "pixel art", t)
    t = re.sub(r"(?i)\b(?:at|in|with)\s+\d{1,3}\s*[x×]\s*\d{1,3}\s*(?:px|pixel(?:s)?|resolution)?\b", "", t)
    t = re.sub(r"(?i)\b(?:tiny|small|large)?\s*(?:\d{1,3}\s*px)\s+(?:resolution|canvas|sprite|icon)\b", "", t)
    t = re.sub(r"(?i)\b(?:low|high)?\s*resolution\b", "", t)
    t = re.sub(r"(?i)\b(?:canvas|sprite|icon)\s+size\s*[:=]?\s*\d{1,3}\b", "", t)
    t = re.sub(r"(?i)\bpixel art\s*,?\s*art\b", "pixel art", t)
    t = re.sub(r"(?i)\bpixel art\s*,\s*pixel art\b", "pixel art", t)
    t = re.sub(r"(?i)\bpixel art\s+pixel art\b", "pixel art", t)
    return re.sub(r"\s+", " ", t).strip(" ,.;")


def zimage_pe_clean_text(text: str) -> str:
    """Collapse SD-style boilerplate into a plain final-description prompt.

    Z-Image Turbo's public prompt-expander rewrites a concise subject description
    into the final visual instruction.  It does not benefit from A1111-style
    prompt cargo such as negative-prompt blocks, quality-tag spam, or runtime
    implementation notes.  Strip those residues and keep only the concrete image
    description.
    """
    t = strip_sprite_resolution_tokens(str(text or ""))
    # Remove explicit negative-prompt sections wholesale before token cleanup so lists like
    # "negative prompt: watermark, text, blurry, ..." do not leak back into the positive prompt.
    t = re.sub(r"(?is)(?:^|[.;,]\s*)(?:negative prompt|negative)\s*:\s*.*$", "", t)
    # Some frontends inline avoid/undesired blocks instead of a separate negative field.
    t = re.sub(r"(?is)(?:^|[.;,]\s*)(?:avoid|undesired|do not include)\s*:\s*(?:watermark|text|logo|blurry|lowres|low resolution|worst quality|bad anatomy|signature|jpeg artifacts)(?:[^.]*)(?:$|\.)", ".", t)
    replacements = [
        (r"\bZ[- ]Image prompt\b[:,]?", ""),
        (r"\bprompt\s*:\s*", ""),
        (r"\bdrawing instruction[s]?\b[:,]?", ""),
        (r"\basset role:\s*\w+\b", ""),
        (r"\bitem fantasy:\s*", "It visually reads as "),
        # Common SD/A1111 boilerplate that adds no concrete visual information for Z-Image.
        (r"\bmasterpiece\b[:,]?", ""),
        (r"\bbest quality\b[:,]?", ""),
        (r"\bhigh quality\b[:,]?", ""),
        (r"\bultra[- ]detailed\b[:,]?", ""),
        (r"\bhighly detailed\b[:,]?", ""),
        (r"\bextremely detailed\b[:,]?", ""),
        (r"\babsurdres\b[:,]?", ""),
        (r"\b8k\b[:,]?", ""),
        (r"\b4k\b[:,]?", ""),
        (r"\blowres\b[:,]?", ""),
        (r"\blow resolution\b[:,]?", ""),
        (r"\blow quality\b[:,]?", ""),
        (r"\bworse quality\b[:,]?", ""),
        (r"\bworst quality\b[:,]?", ""),
        (r"\bbad anatomy\b[:,]?", ""),
        (r"\bjpeg artifacts\b[:,]?", ""),
        (r"\bsignature\b[:,]?", ""),
        (r"\bwatermark\b[:,]?", ""),
        (r"\bno watermark\b[:,]?", ""),
        (r"\bno text(?:\s*,\s*letters\s*,\s*logos\s*,\s*or\s*UI marks)?\b[:,]?", "without letters, logos, or UI marks"),
        (r"\btext[- ]free\b", "without letters, logos, or UI marks"),
        (r"\bpixel perfect\b[:,]?", "crisp pixel-art"),
        (r"\bcentered composition\b[:,]?", ""),
        (r"\bsingle sprite sheet\b[:,]?", "single sprite"),
        # Runtime / engine phrasing -> concrete visual phrasing.
        (r"\bcode handles shot count/spread/splits, do not draw multiple arrows inside one PNG\b", "the visible texture shows one projectile body"),
        (r"\bruntime code handles\b", "the visible texture keeps"),
        (r"\bcode handles\b", "the visible texture keeps"),
        (r"\bfor runtime rotation\b", "along its length"),
        (r"\bwith no huge empty border\b", "while keeping the subject large in frame"),
        (r"\bno oversized empty icon\b", "with the subject kept large in frame"),
        (r"\bno magic glow\b", "without magical glow"),
        (r"\bno coin silhouette\b", "without a coin silhouette"),
        (r"\bno readable letters, numbers, logo marks, UI labels, or symbols\b", "without text, logos, or UI marks"),
        (r"\bzero readable letters, numbers, logo marks, UI labels, or symbols\b", "without text, logos, or UI marks"),
    ]
    for pat, repl in replacements:
        t = re.sub(pat, repl, t, flags=re.IGNORECASE)
    # Remove leftover comma-soup fragments from stripped SD boilerplate.
    t = re.sub(r"(?i)(?:^|[\s,;])(?:watermark|signature|logo|text|blurry|lowres|low resolution|worst quality|bad anatomy|jpeg artifacts)(?=$|[\s,;])", " ", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s*,\s*,+", ", ", t)
    t = re.sub(r"\s*\.\s*\.\s*", ". ", t)
    t = re.sub(r"\s*[,;]\s*(?:[,;]\s*)+", ", ", t)
    t = re.sub(r"(?:^|[.;])\s*(?:,\s*)+", ". ", t)
    t = re.sub(r"\s+", " ", t).strip(" ,.;")
    return t

def truncate_prompt_at_boundary(text: str, limit: int) -> str:
    """Trim prompt text without leaving a broken word or half instruction."""
    value = re.sub(r"\s+", " ", str(text or "")).strip(" ,.;")
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    window = value[:limit + 1]
    minimum = max(24, int(limit * 0.55))
    cut = -1
    for separator in (". ", "; ", ", ", " "):
        candidate = window.rfind(separator)
        if candidate >= minimum:
            cut = candidate + (1 if separator != " " else 0)
            break
    if cut < 0:
        cut = limit
    return value[:cut].rstrip(" ,.;")


def compact_zimage_asset_prompt(parts: list[str], role: str, limit: int = 1800) -> str:
    """Build a subject-first prompt while preserving the final technical guard.

    Character slicing used to cut prompts mid-sentence and could remove the chroma/one-
    subject guard entirely. The last part is the caller-owned technical guard; reserve it
    and compact only the descriptive body. No item semantics are added here.
    """
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in parts:
        t = zimage_pe_clean_text(re.sub(r"\s+", " ", str(raw or "")).strip(" ,.;"))
        if not t:
            continue
        key = re.sub(r"\s+", " ", t.lower())
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(t)
    if not cleaned:
        raise ValueError(f"{role}: explicit non-empty image prompt content required")

    if len(cleaned) == 1:
        return truncate_prompt_at_boundary(cleaned[0], max(1, limit - 1)).rstrip(".") + "."

    guard = cleaned[-1].rstrip(".")
    reserved = min(len(guard), max(120, limit // 2))
    if len(guard) > reserved:
        guard = truncate_prompt_at_boundary(guard, reserved)
    body_limit = max(1, limit - len(guard) - 3)
    body = truncate_prompt_at_boundary(". ".join(cleaned[:-1]), body_limit)
    prompt = ". ".join(part for part in (body, guard) if part).strip(" .")
    return prompt + "."