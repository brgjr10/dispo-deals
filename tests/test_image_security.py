"""Regression tests for download_image SSRF / resource guards.

All network calls are mocked: socket.getaddrinfo and requests.get are
replaced with fakes so no real connection is ever made.
"""
import types

import socket

import pytest

import utils.images as images


class _FakeResponse:
    """Minimal stand-in for requests.Response used by download_image."""

    def __init__(self, content=b"", status_code=200, headers=None, raise_on_read=False):
        self.status_code = status_code
        self.headers = headers or {}
        self._content = content
        self._raised = raise_on_read
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=65536):
        if self._raised:
            raise Exception("stream error")
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i : i + chunk_size]

    def close(self):
        self.closed = True


def _addrinfo_for(host_ip):
    """Build a socket.getaddrinfo-style result resolving host to host_ip."""
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (host_ip, 80)),
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (host_ip, 0, 0, 0)),
    ]


def _patch(monkeypatch, host_ip="93.184.216.34", content=b"img", status_code=200,
         headers=None, stream_error=False):
    headers = headers or {"Content-Type": "image/jpeg"}
    _resp_headers = headers
    monkeypatch.setattr(
        images.socket,
        "getaddrinfo",
        lambda host, port, *a, **k: _addrinfo_for(host_ip),
    )
    monkeypatch.setattr(
        images.requests,
        "get",
        lambda url, headers=None, timeout=None, stream=True, _h=_resp_headers:
            _FakeResponse(
                content=content, status_code=status_code, headers=_h,
                raise_on_read=stream_error,
            ),
    )


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


def test_pins_connection_to_validated_ip(monkeypatch):
    captured = {}

    def fake_getaddrinfo(host, port, *a, **k):
        captured["resolved_host"] = host
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]

    def fake_get(url, headers=None, timeout=None, stream=True):
        captured["url"] = url
        captured["headers"] = headers
        return _FakeResponse(content=b"\xff\xd8\xff", headers={"Content-Type": "image/jpeg"})

    monkeypatch.setattr(images.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(images.requests, "get", fake_get)

    images.download_image("http://example.com/logo.jpg")

    # The socket connected to the pinned IP, not the name.
    assert "93.184.216.34" in captured["url"]
    assert "example.com" not in captured["url"].split("//", 1)[1].split("/", 1)[0]
    # The original host is preserved as the Host header for vhosting.
    assert captured["headers"]["Host"] == "example.com"


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
