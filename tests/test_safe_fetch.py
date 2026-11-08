import pytest
import requests

from app.net.safe_fetch import (
    FetchError,
    SafeFetcher,
    UnsafeUrlError,
    validate_public_url,
)

PUBLIC = ["93.184.216.34"]


def resolver(mapping: dict[str, list[str]]):
    def resolve(host: str):
        if host not in mapping:
            raise OSError("no such host")
        return mapping[host]

    return resolve


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "ftp://example.com",
        "example.com",
        "https://user:pw@example.com",
        "https://example.com:8443/x",
        "https://localhost/x",
        "https://app.localhost/x",
        "https://db.internal/x",
        "https://printer.local/x",
        "https://127.0.0.1/x",
        "https://[::1]/x",
        "https://10.0.0.5/x",
        "https://192.168.1.10/x",
        "https://169.254.169.254/latest/meta-data",
        "https://100.64.0.1/x",
        "https://0.0.0.0/x",
        "https://[fd00::1]/x",
        "https://rebind.example.com/x",  # resolves to a private address below
        "https://mixed.example.com/x",  # one public and one private address
        "https://nxdomain.example.com/x",
        "",
    ],
)
def test_unsafe_urls_are_refused(url: str) -> None:
    resolve = resolver(
        {
            "rebind.example.com": ["10.1.2.3"],
            "mixed.example.com": ["93.184.216.34", "127.0.0.1"],
            "example.com": PUBLIC,
        }
    )
    with pytest.raises(UnsafeUrlError):
        validate_public_url(url, resolve)


def test_public_https_urls_pass() -> None:
    assert validate_public_url(
        "https://example.com/pricing?x=1", resolver({"example.com": PUBLIC})
    ) == ("https://example.com/pricing?x=1")
    assert validate_public_url("https://93.184.216.34/", resolver({})).startswith("https://")
    assert validate_public_url("https://example.com:443/", resolver({"example.com": PUBLIC}))


class Response:
    def __init__(self, status=200, headers=None, body=b"", encoding="utf-8") -> None:
        self.status_code = status
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}
        self._body = body
        self.encoding = encoding
        self.closed = False
        self.chunks_read = 0

    def iter_content(self, chunk_size=1):
        for start in range(0, len(self._body), chunk_size):
            self.chunks_read += 1
            yield self._body[start : start + chunk_size]

    def close(self) -> None:
        self.closed = True


class Session:
    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def get(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def fetcher(session, **kwargs) -> SafeFetcher:
    mapping = {"example.com": PUBLIC, "www.example.com": PUBLIC, "evil.test": ["10.0.0.9"]}
    return SafeFetcher(session=session, resolver=resolver(mapping), **kwargs)


def test_fetches_html_without_following_redirects_automatically() -> None:
    session = Session(Response(body=b"<html><title>Acme</title></html>"))
    page = fetcher(session).fetch("https://example.com/")

    assert page.content_type == "text/html" and "Acme" in page.text
    call = session.calls[0]
    assert call["allow_redirects"] is False and call["stream"] is True and call["timeout"] == 10.0
    assert "unMeetBot" in call["headers"]["User-Agent"]


def test_every_redirect_hop_is_validated_again() -> None:
    session = Session(Response(302, {"Location": "https://evil.test/internal"}))
    with pytest.raises(UnsafeUrlError):
        fetcher(session).fetch("https://example.com/")
    assert len(session.calls) == 1  # the private hop was never requested

    metadata = Session(Response(302, {"Location": "https://169.254.169.254/"}))
    with pytest.raises(UnsafeUrlError):
        fetcher(metadata).fetch("https://example.com/")
    downgrade = Session(Response(302, {"Location": "http://example.com/"}))
    with pytest.raises(UnsafeUrlError):
        fetcher(downgrade).fetch("https://example.com/")


def test_valid_redirects_are_followed_up_to_three_hops() -> None:
    ok = Session(
        Response(301, {"Location": "https://www.example.com/"}),
        Response(302, {"Location": "/home"}),
        Response(body=b"<p>hello</p>"),
    )
    page = fetcher(ok).fetch("https://example.com/")
    assert page.url == "https://www.example.com/home"

    loop = Session(*[Response(302, {"Location": "https://example.com/"}) for _ in range(4)])
    with pytest.raises(FetchError, match="too many redirects"):
        fetcher(loop).fetch("https://example.com/")
    with pytest.raises(FetchError, match="location"):
        fetcher(Session(Response(302, {}))).fetch("https://example.com/")


@pytest.mark.parametrize(
    "response,message",
    [
        (Response(404), "HTTP 404"),
        (Response(500), "HTTP 500"),
        (Response(200, {"Content-Type": "application/pdf"}, b"%PDF"), "not an HTML page"),
        (Response(200, {"Content-Type": "image/png"}, b"x"), "not an HTML page"),
        (Response(200, {"X-Other": "1"}, b"x"), "not an HTML page"),
    ],
)
def test_error_statuses_and_non_html_are_rejected(response, message) -> None:
    with pytest.raises(FetchError, match=message):
        fetcher(Session(response)).fetch("https://example.com/")
    assert response.closed


def test_network_errors_become_fetch_errors() -> None:
    with pytest.raises(FetchError):
        fetcher(Session(requests.ConnectionError("boom"))).fetch("https://example.com/")


def test_large_pages_are_cut_and_reading_stops_early() -> None:
    response = Response(body=b"a" * 200_000)
    page = fetcher(Session(response), max_bytes=50_000).fetch("https://example.com/")
    assert len(page.text) == 50_000
    assert response.chunks_read < 13  # 200_000 / 16_384 would be 13 chunks
    assert response.closed


def test_plain_text_and_encoding_fallback() -> None:
    page = fetcher(
        Session(
            Response(
                headers={"Content-Type": "text/plain"},
                body="caffè".encode("latin-1"),
                encoding="utf-8",
            )
        )
    ).fetch("https://example.com/")
    assert page.content_type == "text/plain" and "caff" in page.text
