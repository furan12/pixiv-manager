"""
Thumbnail generation and caching using Pillow.
Generates thumbnails on-demand and caches them to disk.
"""
import hashlib
from pathlib import Path

from PIL import Image, ImageOps

THUMB_FORMAT = "JPEG"
THUMB_QUALITY = 75


def _thumb_key(file_path: Path, size: tuple[int, int]) -> str:
    """Generate a unique cache key for a file + size combination."""
    raw = f"{file_path.resolve()}:{size[0]}x{size[1]}"
    mtime = file_path.stat().st_mtime if file_path.exists() else 0
    raw += f":{mtime}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def get_thumbnail(
    file_path: Path,
    cache_dir: Path,
    size: tuple[int, int] = (300, 300),
) -> Path:
    """
    Get a thumbnail for the given image file.
    Returns the path to the cached thumbnail, generating it if needed.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _thumb_key(file_path, size)
    thumb_path = cache_dir / f"{key}.jpg"

    # Return cached if it exists and is newer than source
    if thumb_path.exists():
        src_mtime = file_path.stat().st_mtime
        cache_mtime = thumb_path.stat().st_mtime
        if cache_mtime >= src_mtime:
            return thumb_path

    # Generate thumbnail
    try:
        img = Image.open(file_path)
        img = ImageOps.exif_transpose(img)  # Respect EXIF orientation
        img.thumbnail(size, Image.LANCZOS)

        # Convert to RGB if necessary (for PNG with alpha, etc.)
        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (30, 30, 30))
            if img.mode == "P":
                img = img.convert("RGBA")
            if img.mode in ("RGBA", "LA"):
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        img.save(thumb_path, THUMB_FORMAT, quality=THUMB_QUALITY)
    except Exception:
        # Return a placeholder or re-raise
        raise

    return thumb_path


def clear_thumbnail_cache(cache_dir: Path):
    """Remove all cached thumbnails."""
    if cache_dir.exists():
        for f in cache_dir.iterdir():
            if f.is_file():
                f.unlink()
