import hashlib
import ipaddress
import logging
import os
import socket
import requests
import urllib3
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse
from PIL import Image
from urllib3.connection import HTTPConnection, HTTPSConnection

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


class _PinnedConnectionMixin:
    """Connect to a pre-validated IP while keeping the hostname for TLS.

    urllib3 keeps the name it resolves (_dns_host) apart from the name it
    presents (host): the second one drives the SNI extension, the certificate
    check and the Host header. Only _dns_host is aimed at the validated
    address, so the request still names the real server - a ClientHello
    without the right server name is answered by every CDN with a handshake
    alert - while the socket cannot be steered to a private address by a
    DNS rebind.
    """

    def __init__(self, *args, pinned_ip: Optional[str] = None, **kwargs):
        self._pinned_ip = pinned_ip
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        # _dns_host is the only place urllib3 resolves the name, so swapping it
        # for the pinned IP moves the TCP connection and nothing else.
        original_dns_host = self._dns_host
        self._dns_host = self._pinned_ip
        try:
            return super()._new_conn()
        finally:
            self._dns_host = original_dns_host


class _PinnedHTTPConnection(_PinnedConnectionMixin, HTTPConnection):
    pass


class _PinnedHTTPSConnection(_PinnedConnectionMixin, HTTPSConnection):
    pass


class _PinnedHTTPConnectionPool(urllib3.HTTPConnectionPool):
    ConnectionCls = _PinnedHTTPConnection


class _PinnedHTTPSConnectionPool(urllib3.HTTPSConnectionPool):
    ConnectionCls = _PinnedHTTPSConnection


class _PinnedHTTPAdapter(requests.adapters.HTTPAdapter):
    """Adapter that validates the target host and pins the socket to it.

    Every request a session makes passes through here, including the hops of
    a redirect, so a redirect cannot be used to reach a private address
    either - each hop is resolved and checked again on its own.
    """

    def get_connection(self, url, proxies=None):
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            raise requests.exceptions.InvalidURL(f"No host in {url!r}")

        ok, pinned_ip = _host_resolves_only_to_public(host)
        if not ok:
            raise requests.exceptions.InvalidURL(
                f"Refusing to download from {host!r}: not a public address"
            )

        # The pool keeps the hostname, so urllib3 sends the right Host header
        # and verifies the certificate against the right name; only the socket
        # is aimed at the validated address.
        if parsed.scheme == "https":
            return _PinnedHTTPSConnectionPool(
                host,
                parsed.port or 443,
                pinned_ip=pinned_ip,
                cert_reqs="CERT_REQUIRED",
                assert_hostname=host,
            )
        return _PinnedHTTPConnectionPool(
            host,
            parsed.port or 80,
            pinned_ip=pinned_ip,
        )


def download_image(url: str, timeout: int = 15) -> Optional[bytes]:
    """Download an image from a URL, rejecting SSRF-prone requests.

    The URL must use http/https, resolve only to public addresses, carry an
    image Content-Type, and stay under the size ceiling. The connection is
    pinned to the validated address so DNS rebind cannot redirect it to a
    private one, while the hostname stays in the request so the TLS handshake
    still names the server.
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

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    session = requests.Session()
    session.mount("http://", _PinnedHTTPAdapter())
    session.mount("https://", _PinnedHTTPAdapter())

    try:
        response = session.get(url, headers=headers, timeout=timeout, stream=True)
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
    finally:
        session.close()


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