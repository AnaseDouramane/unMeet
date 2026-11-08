"""Fetch a public web page without letting a user point the server at internal services.

Rules: https only; the hostname must resolve to public addresses only (loopback, private,
link-local, metadata and reserved ranges are refused); redirects are followed by hand, at most
three, and every hop is validated again; the response is read in a bounded stream; only
HTML/text is accepted.

Limit: the hostname is resolved by us and again by the HTTP stack when it connects, so a
hostile DNS server could answer differently the second time (DNS rebinding). The check closes
the common cases; keep the fetcher on a network without access to internal services too.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

Resolver = Callable[[str], Sequence[str]]

MAX_BYTES = 1_000_000
MAX_REDIRECTS = 3


class UnsafeUrlError(ValueError):
    """The URL is not an acceptable public https address."""


class FetchError(RuntimeError):
    """The page could not be retrieved."""


@dataclass(frozen=True)
class FetchedPage:
    url: str
    content_type: str
    text: str


def _default_resolver(hostname: str) -> Sequence[str]:
    return [str(info[4][0]) for info in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)]


def validate_public_url(url: str, resolver: Resolver = _default_resolver) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        raise UnsafeUrlError("only absolute https URLs are accepted")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URLs with credentials are not accepted")
    if parsed.port not in (None, 443):
        raise UnsafeUrlError("only the default https port is accepted")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan")):
        raise UnsafeUrlError("the host must be public")
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
        addresses: Sequence[str] = [str(literal)]
    except ValueError:
        try:
            addresses = resolver(host)
        except OSError as error:
            raise UnsafeUrlError("the host could not be resolved") from error
    if not addresses:
        raise UnsafeUrlError("the host could not be resolved")
    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise UnsafeUrlError("the host must resolve to public addresses only")
    return parsed.geturl()


class SafeFetcher:
    def __init__(
        self,
        session: Any | None = None,
        resolver: Resolver = _default_resolver,
        timeout_seconds: float = 10.0,
        user_agent: str = "unMeetBot/0.1 (+site analysis requested by the site owner)",
        max_bytes: int = MAX_BYTES,
    ) -> None:
        self._session = session or requests.Session()
        self._resolver = resolver
        self._timeout = timeout_seconds
        self._user_agent = user_agent
        self._max_bytes = max_bytes

    def fetch(self, url: str) -> FetchedPage:
        current = validate_public_url(url, self._resolver)
        for _ in range(MAX_REDIRECTS + 1):
            try:
                response = self._session.get(
                    current,
                    headers={"User-Agent": self._user_agent, "Accept": "text/html,text/plain"},
                    timeout=self._timeout,
                    allow_redirects=False,
                    stream=True,
                )
            except requests.RequestException as error:
                raise FetchError(f"could not fetch the page: {error}") from error
            try:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    if not location:
                        raise FetchError("redirect without a location")
                    current = validate_public_url(urljoin(current, location), self._resolver)
                    continue
                if response.status_code >= 400:
                    raise FetchError(f"the site answered HTTP {response.status_code}")
                content_type = (
                    response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                )
                if content_type not in ("text/html", "application/xhtml+xml", "text/plain"):
                    raise FetchError("the URL is not an HTML page")
                body = bytearray()
                for chunk in response.iter_content(chunk_size=16384):
                    body.extend(chunk)
                    if len(body) > self._max_bytes:
                        break  # enough: only the start of the page matters
                text = bytes(body[: self._max_bytes]).decode(
                    response.encoding or "utf-8", errors="replace"
                )
                return FetchedPage(current, content_type, text)
            finally:
                response.close()
        raise FetchError("too many redirects")
