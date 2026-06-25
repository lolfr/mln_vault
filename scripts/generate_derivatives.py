#!/usr/bin/env python3
"""Generate thumbnail (256px) and preview (1200px) derivatives.

Supports:
- raster images via Pillow
- EPS/PDF via macOS `sips` (first page)
- videos via ffmpeg (poster frame at 10%)
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageOps

try:
    from . import common  # when imported as module
except ImportError:
    import common  # when run as script (sys.path includes script dir)

THUMB_SIZE = 256
PREVIEW_SIZE = 1200
JPEG_Q_THUMB = 80
JPEG_Q_PREVIEW = 82

FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"
SIPS = "/usr/bin/sips"


def _save_jpeg(im: Image.Image, dst: Path, size: int, q: int) -> None:
    im = ImageOps.exif_transpose(im)
    im.thumbnail((size, size), Image.Resampling.LANCZOS)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, "JPEG", quality=q, optimize=True, progressive=True)


def _image_dims(src: Path) -> tuple[int | None, int | None]:
    try:
        with Image.open(src) as im:
            return im.size  # (w, h)
    except Exception:
        return (None, None)


def _from_raster(src: Path, thumb: Path, preview: Path) -> dict:
    with Image.open(src) as im:
        w, h = im.size
        _save_jpeg(im.copy(), preview, PREVIEW_SIZE, JPEG_Q_PREVIEW)
        _save_jpeg(im.copy(), thumb, THUMB_SIZE, JPEG_Q_THUMB)
    return {"width_px": w, "height_px": h}


def _from_vector(src: Path, thumb: Path, preview: Path) -> dict:
    """Use sips to rasterize EPS/PDF first page to a temp JPEG, then Pillow."""
    thumb.parent.mkdir(parents=True, exist_ok=True)
    preview.parent.mkdir(parents=True, exist_ok=True)
    tmp = preview.with_suffix(".tmp.jpg")
    subprocess.run(
        [SIPS, "-s", "format", "jpeg", "-Z", str(PREVIEW_SIZE * 2),
         str(src), "--out", str(tmp)],
        check=True, capture_output=True,
    )
    result = _from_raster(tmp, thumb, preview)
    tmp.unlink(missing_ok=True)
    return result


def _video_meta(src: Path) -> dict:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,duration:format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(src)],
        capture_output=True, text=True,
    )
    lines = [l for l in out.stdout.strip().splitlines() if l and l != "N/A"]
    w = h = None
    duration = None
    if len(lines) >= 3:
        try:
            w = int(lines[0])
            h = int(lines[1])
            duration = float(lines[2])
        except ValueError:
            pass
    return {"width_px": w, "height_px": h, "duration_seconds": duration}


def _from_video(src: Path, thumb: Path, preview: Path) -> dict:
    meta = _video_meta(src)
    duration = meta.get("duration_seconds") or 10.0
    seek = max(1.0, duration * 0.1)
    preview.parent.mkdir(parents=True, exist_ok=True)
    thumb.parent.mkdir(parents=True, exist_ok=True)
    # Preview poster
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-ss", f"{seek:.2f}",
         "-i", str(src),
         "-frames:v", "1",
         "-vf", f"scale='min({PREVIEW_SIZE},iw)':-2",
         "-q:v", "3", str(preview)],
        check=True, capture_output=True,
    )
    # Thumb: re-scale from the preview (cheap)
    with Image.open(preview) as im:
        _save_jpeg(im, thumb, THUMB_SIZE, JPEG_Q_THUMB)
    return meta


def derive(src: Path, item_id: str) -> dict:
    """Generate derivatives for src, return {thumb_path, preview_path, width_px, height_px, duration_seconds}."""
    ext = src.suffix.lower()
    thumb = common.THUMBS_ROOT / f"{item_id}.jpg"
    preview = common.PREVIEW_ROOT / f"{item_id}.jpg"

    if ext in common.IMAGE_EXTS:
        meta = _from_raster(src, thumb, preview)
    elif ext in common.VECTOR_EXTS:
        meta = _from_vector(src, thumb, preview)
    elif ext in common.VIDEO_EXTS:
        meta = _from_video(src, thumb, preview)
    else:
        return {"thumb": None, "preview": None}

    return {
        "thumb": str(thumb.relative_to(common.ARCHIVE_ROOT)),
        "preview": str(preview.relative_to(common.ARCHIVE_ROOT)),
        "width_px": meta.get("width_px"),
        "height_px": meta.get("height_px"),
        "duration_seconds": meta.get("duration_seconds"),
    }


if __name__ == "__main__":
    import sys
    src = Path(sys.argv[1])
    item_id = sys.argv[2] if len(sys.argv) > 2 else "test"
    print(derive(src, item_id))
