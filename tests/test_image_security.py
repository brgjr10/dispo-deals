"""Regression tests for download_image SSRF / resource guards.

No real connection is ever made: name resolution and the HTTP layer are
replaced with fakes.
"""
import socket

import pytest
import urllib3
import urllib3.util.connection

import utils.images as images


class _FakeHTTPResponse:
    """Minimal stand-in for urllib3.HTTPResponse as requests consumes it."""

    def __init__(self, content=b"", status=200, headers=None, reason="OK"):
        self._content = content
        self.status = status
        self.headers = headers or {}
        self.reason = reason
        # requests skips cookie extraction when there is no original response.
        self._original_response = None

    def stream(self, chunk_size=65536, decode_content=True):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i : i + chunk_size]

    def read(self, amt=None, decode_content=None, cache_content=False):
        return self._content

    def release_conn(self):
        pass

    def close(self):
        pass


def _addrinfo_for(host_ip):
    """Build a socket.getaddrinfo-style result resolving host to host_ip."""
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (host_ip, 80)),
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (host_ip, 0, 0, 0)),
    ]


def _patch(monkeypatch, host_ip="93.184.216.34", content=b"img", status=200,
           headers=None):
    headers = headers or {"Content-Type": "image/jpeg"}
    _resp_headers = headers
    monkeypatch.setattr(
        images.socket,
        "getaddrinfo",
        lambda host, port, *a, **k: _addrinfo_for(host_ip),
    )

    response = _FakeHTTPResponse(content=content, status=status, headers=_resp_headers)

    def fake_urlopen(self, method=None, url=None, **kwargs):
        return response

    monkeypatch.setattr(urllib3.connectionpool.HTTPConnectionPool, "urlopen", fake_urlopen)


def test_blocks_localhost(monkeypatch):
    _patch(monkeypatch, host_ip="127.0.0.1")
    assert images.download_image("http://127.0.0.1/x.jpg") is None


def test_blocks_link_local_metadata(monkeypatch):
    _patch(monkeypatch, host_ip="169.254.169.254")
    assert images.download_image("http://169.254.169.254/latest/meta-data/") is None


def test_blocks_rfc1918(monkeypatch):
    for host in ("10.0.0.1", "172.16.0.1", "192.168.1.1"):
        _patch(monkeypatch, host_ip=host)
        assert images.download_image(f"http://{host}/x.jpg") is None


def test_blocks_ipv6_localhost(monkeypatch):
    _patch(monkeypatch, host_ip="::1")
    assert images.download_image("http://[::1]/x.jpg") is None


def test_blocks_file_scheme(monkeypatch):
    _patch(monkeypatch, host_ip="93.184.216.34")
    assert images.download_image("file:///etc/passwd") is None
    assert images.download_image("ftp://example.com/x.jpg") is None


def test_allows_public_image(monkeypatch):
    _patch(monkeypatch, host_ip="93.184.216.34", content=b"\xff\xd8\xffimg")
    result = images.download_image("http://example.com/logo.jpg")
    assert result == b"\xff\xd8\xffimg"


def test_blocks_non_image_content_type(monkeypatch):
    _patch(monkeypatch, host_ip="93.184.216.34", content=b"<html>",
           headers={"Content-Type": "text/html"})
    assert images.download_image("http://example.com/evil.html") is None


def test_blocks_oversized_image(monkeypatch):
    big = b"\xff\xd8\xff" + b"0" * (images._MAX_CONTENT_BYTES + 1)
    _patch(monkeypatch, host_ip="93.184.216.34", content=big)
    assert images.download_image("http://example.com/big.jpg") is None


def test_unresolvable_host_return_none(monkeypatch):
    monkeypatch.setattr(images.socket, "getaddrinfo",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no such host")))
    assert images.download_image("http://does-not-exist.invalid/x.jpg") is None


def test_mixed_private_and_public_address_blocked(monkeypatch):
    # One public and one private address for the same name must still block.
    def fake_getaddrinfo(host, port, *a, **k):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 80)),
        ]
    monkeypatch.setattr(images.socket, "getaddrinfo", fake_getaddrinfo)
    assert images.download_image("http://example.com/x.jpg") is None


def test_request_keeps_the_hostname_for_tls(monkeypatch):
    """The request has to name the host, not the bare IP.

    The TLS handshake negotiates the server name (SNI) and the certificate is
    checked against it, so a request aimed at the IP is answered by every CDN
    with a handshake alert instead of an image.
    """
    monkeypatch.setattr(images.socket, "getaddrinfo",
                        lambda host, port, *a, **k: _addrinfo_for("93.184.216.34"))

    pool = images._PinnedHTTPAdapter().get_connection("https://example.com/logo.jpg")

    assert pool.host == "example.com"
    assert pool.port == 443
    assert pool.conn_kw["pinned_ip"] == "93.184.216.34"


def test_connection_targets_the_validated_ip(monkeypatch):
    """The socket goes to the validated address while the name stays put."""
    captured = {}

    def fake_create_connection(address, *args, **kwargs):
        captured["address"] = address
        return object()

    monkeypatch.setattr(urllib3.util.connection, "create_connection", fake_create_connection)

    conn = images._PinnedHTTPSConnection(
        host="example.com", port=443, pinned_ip="93.184.216.34"
    )
    conn._new_conn()

    assert captured["address"] == ("93.184.216.34", 443)
    # The presented name is untouched, so SNI, the certificate check and the
    # Host header all still say example.com.
    assert conn.host == "example.com"
    assert conn._dns_host == "example.com"


def test_adapter_refuses_a_private_host(monkeypatch):
    """Every hop is checked, so a redirect cannot reach a private address."""
    monkeypatch.setattr(images.socket, "getaddrinfo",
                        lambda host, port, *a, **k: _addrinfo_for("192.168.1.1"))

    with pytest.raises(Exception):
        images._PinnedHTTPAdapter().get_connection("https://example.com/logo.jpg")
