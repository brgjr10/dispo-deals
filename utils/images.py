import hashlib
import logging
import os
import requests
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image

logger = logging.getLogger(__name__)


def download_image(url: str, timeout: int = 15) -> Optional[bytes]:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=timeout, stream=True)
        response.raise_for_status()
        return response.content
    except Exception as e:
        logger.warning(f"Failed to download image from {url}: {e}")
        return None


def resize_image(image_data: bytes, max_width: int = 800, max_size_kb: int = 500) -> bytes:
    try:
        img = Image.open(BytesIO(image_data))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

        output = BytesIO()
        quality = 85
        while quality > 10:
            output.seek(0)
            output.truncate()
            img.save(output, format="JPEG", quality=quality, optimize=True)
            if len(output.getvalue()) <= max_size_kb * 1024:
                break
            quality -= 5

        return output.getvalue()
    except Exception as e:
        logger.warning(f"Failed to resize image: {e}")
        return image_data


def get_mime_type(image_data: bytes) -> str:
    if image_data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    elif image_data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    elif image_data.startswith(b"GIF87a") or image_data.startswith(b"GIF89a"):
        return "image/gif"
    elif image_data.startswith(b"RIFF") and b"WEBP" in image_data[:12]:
        return "image/webp"
    return "image/jpeg"


def hash_url(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def save_image_cache(image_data: bytes, cache_dir: str, url_hash: str) -> str:
    os.makedirs(cache_dir, exist_ok=True)
    mime = get_mime_type(image_data)
    ext = ".jpg" if mime == "image/jpeg" else ".png"
    filepath = Path(cache_dir) / f"{url_hash}{ext}"
    with open(filepath, "wb") as f:
        f.write(image_data)
    return str(filepath)


def load_image_cache(cache_dir: str, url_hash: str) -> Optional[bytes]:
    for ext in [".jpg", ".png", ".webp"]:
        filepath = Path(cache_dir) / f"{url_hash}{ext}"
        if filepath.exists():
            with open(filepath, "rb") as f:
                return f.read()
    return None