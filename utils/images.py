import hashlib
import ipaddress
import logging
import os
import socket
import requests
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse
from PIL import Image

logger = logging.getLogger(__name__)

# Only http(s) images are fetched. Everything else (file://, ftp://, javascript:,
# data: ...) is rejected before any network call.
_ALLOWED_SCHEMES = ("http", "https")

# Private / reserved / link-local / multicast ranges that must never be reached
# by the image fetcher. A single matching address blocks the whole host so a
# DNS-rebind cannot slip a private address in after a public one validates.
_PRIVATE_NETS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
)

# Ceiling on downloaded bytes so one oversized image cannot exhaust memory.
_MAX_CONTENT_BYTES = 10 * 1024 * 1024  # 10 MB


def _host_resolves_only_to_public(host: str) -> tuple[bool, str | None]:
    """Return (ok, pinned_ip).

    Resolves the host once and pins the first public address. Returns
    (False, None) when the host cannot be resolved or any resolved address is
    private/reserved, so a DNS-rebind cannot later steer the connection
    inward. Pinned IP is returned so callers can connect directly to it.
    """
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        logger.warning(f"Unable to resolve host {host!r}; refusing request")
        return False, None

    pinned = None
    for family, _type, _proto, _canonname, sockaddr in infos:
        addr = sockaddr[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if any(ip in net for net in _PRIVATE_NETS):
            logger.warning(f"Host {host!r} resolves to private/reserved address {addr}; refusing request")
            return False, None
        if pinned is None:
            pinned = addr

    if pinned is None:
        logger.warning(f"Host {host!r} resolved no usable address; refusing request")
        return False, None

    return True, pinned


def _pinned_url(url: str, pinned_ip: str) -> str:
    """Rewrite the URL netloc to the pinned IP while keeping the original Host.

    Connecting directly to the validated IP defeats DNS rebind: even if the
    name later resolves to a private address, the socket is already bound to
    the public address we checked.
    """
    parsed = urlparse(url)
    netloc = pinned_ip
    if parsed.port is not None:
        netloc = f"{pinned_ip}:{parsed.port}"
    return parsed._replace(netloc=netloc).geturl()


def download_image(url: str, timeout: int = 15) -> Optional[bytes]:
    """Download an image from a URL, rejecting SSRF-prone requests.

    The URL must use http/https, resolve only to public addresses, carry an
    image Content-Type, and stay under the size ceiling. The connection is
    pinned to the first resolved public IP so DNS rebind cannot redirect to a
    private address after validation.
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        logger.warning(f"Failed to parse image URL {url!r}: {e}")
        return None

    if parsed.scheme not in _ALLOWED_SCHEMES:
        logger.warning(f"Blocked image URL with non-http(s) scheme {parsed.scheme!r}: {url}")
        return None

    host = parsed.hostname
    if not host:
        logger.warning(f"Blocked image URL with no host: {url}")
        return None

    ok, pinned_ip = _host_resolves_only_to_public(host)
    if not ok:
        return None

    # Pin the connection to the validated public IP; keep the original host as
    # the Host header so virtual-hosted servers still work.
    pinned = _pinned_url(url, pinned_ip)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Host": host,
    }

    try:
        response = requests.get(
            pinned, headers=headers, timeout=timeout, stream=True
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if not content_type.lower().startswith("image/"):
            logger.warning(
                f"Blocked image URL with non-image Content-Type {content_type!r}: {url}"
            )
            response.close()
            return None

        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > _MAX_CONTENT_BYTES:
                logger.warning(
                    f"Blocked image URL exceeding {_MAX_CONTENT_BYTES} bytes: {url}"
                )
                response.close()
                return None
            chunks.append(chunk)
        return b"".join(chunks)
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