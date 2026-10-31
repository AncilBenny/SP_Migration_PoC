"""Bounded Microsoft Graph v1.0 file transport for a supplied, authorized token.

Does not acquire credentials: caller injects token_provider. No tenant access by
imports or tests. Graph auth is sent ONLY to graph.microsoft.com; a Graph 302
is followed at most once, WITHOUT Authorization and only to an allowlisted
public HTTPS host. DNS address is pinned into the TLS connection; no ambient
HTTP proxy or automatic redirects. Temporary URLs and tokens are never logged.
"""
from __future__ import annotations

from dataclasses import dataclass
import http.client
import ipaddress
import re
import socket
import ssl
import time
from typing import Callable
from urllib.parse import urlsplit

from .acquisition import MAX_FILE_BYTES
from .graph_assets import _identity

GRAPH_HOST = 'graph.microsoft.com'
MAX_RETRIES = 2
MAX_RETRY_AFTER = 30
MAX_REDIRECT_CHARS = 8192
RETRYABLE = {429, 500, 502, 503, 504}
SAFE_ERROR = re.compile(r'^GRAPH_[A-Z0-9_]{1,64}$')


class GraphTransferError(ValueError):
    """Contains a fixed diagnostic code only; no bearer or signed URL data."""

    def __init__(self, code: str):
        super().__init__(code if SAFE_ERROR.fullmatch(code) else 'GRAPH_TRANSPORT_FAILED')


@dataclass(frozen=True)
class HttpResult:
    status: int
    headers: dict[str, str]
    body: bytes

    def header(self, key: str) -> str:
        return self.headers.get(key.lower(), '')


def validate_public_host(hostname: str, allowed_hosts: set[str]) -> bool:
    """Exact hostname match; never suffix-match wildcard parents."""
    if not hostname or len(hostname) > 253 or not isinstance(allowed_hosts, set):
        return False
    try:
        normalized = hostname.encode('idna').decode('ascii').lower()
    except UnicodeError:
        return False
    return normalized in allowed_hosts and normalized != GRAPH_HOST and bool(re.fullmatch(r'[a-z0-9.-]+', normalized))


def _location(value: str, allowed_hosts: set[str]) -> tuple[str, str]:
    """Validate URL without ever returning it in an error."""
    if not isinstance(value, str) or not (1 <= len(value) <= MAX_REDIRECT_CHARS):
        raise GraphTransferError('GRAPH_REDIRECT_INVALID')
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in value) or '\\' in value:
        raise GraphTransferError('GRAPH_REDIRECT_INVALID')
    try:
        parts = urlsplit(value)
        host = (parts.hostname or '').lower()
        if (parts.scheme != 'https' or parts.username or parts.password or parts.port not in (None, 443)
            or not parts.path.startswith('/') or not validate_public_host(host, allowed_hosts)
            or parts.fragment):
            raise GraphTransferError('GRAPH_REDIRECT_HOST_DENIED')
        return host, value
    except ValueError:
        raise GraphTransferError('GRAPH_REDIRECT_INVALID') from None


def _resolve_public_ip(host: str) -> str:
    try:
        rows = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = [row[4][0] for row in rows]
        if not addresses or not all(ipaddress.ip_address(ip).is_global for ip in addresses):
            raise GraphTransferError('GRAPH_DNS_NONPUBLIC_ADDRESS')
        return addresses[0]
    except GraphTransferError:
        raise
    except (socket.gaierror, ValueError):
        raise GraphTransferError('GRAPH_DNS_RESOLUTION_FAILED') from None


class _PinnedHTTPS(http.client.HTTPSConnection):
    """Connect to prevalidated IP, verify certificate against original hostname."""

    def __init__(self, host: str, ip: str, timeout: int):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self._approved_ip = ip

    def connect(self):
        sock = socket.create_connection((self._approved_ip, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def _https_request(url: str, headers: dict[str, str], max_bytes: int, timeout: int) -> HttpResult:
    """Production default HTTP executor: no redirects/proxies; DNS-pin + TLS verify."""
    parts = urlsplit(url)
    host = parts.hostname
    if not host or parts.scheme != 'https' or parts.port not in (None, 443):
        raise GraphTransferError('GRAPH_REQUEST_INVALID')
    ip = _resolve_public_ip(host)
    conn = _PinnedHTTPS(host, ip, timeout)
    path = (parts.path or '/') + (('?' + parts.query) if parts.query else '')
    try:
        conn.request('GET', path, headers={**headers, 'Accept-Encoding': 'identity'})
        response = conn.getresponse()
        # Check size before reading, but never trust Content-Length as final proof.
        length = response.getheader('Content-Length')
        if length is not None and length.isdecimal() and int(length) > max_bytes:
            raise GraphTransferError('GRAPH_BINARY_TOO_LARGE')
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise GraphTransferError('GRAPH_BINARY_TOO_LARGE')
        return HttpResult(response.status, {k.lower(): v for k, v in response.getheaders()}, body)
    finally:
        conn.close()


class GraphBinaryFetcher:
    """Callable adapter compatible with stage_graph_files(fetcher=...).

    Only a server-side job should provide token_provider. No automatic token
    caching, URL persistence, tenant discovery, destination upload or web UI.
    """

    def __init__(self, token_provider: Callable[[], str], *, redirect_hosts: set[str],
                 executor: Callable[[str, dict[str, str], int, int], HttpResult] | None = None,
                 sleeper: Callable[[float], None] = time.sleep, timeout: int = 20,
                 max_file_bytes: int = MAX_FILE_BYTES):
        if not callable(token_provider):
            raise GraphTransferError('GRAPH_TOKEN_PROVIDER_REQUIRED')
        if not redirect_hosts or not isinstance(redirect_hosts, set) or any(
                not isinstance(h, str) or not validate_public_host(h, redirect_hosts) for h in redirect_hosts):
            raise GraphTransferError('GRAPH_REDIRECT_ALLOWLIST_REQUIRED')
        if type(max_file_bytes) is not int or max_file_bytes < 1 or max_file_bytes > MAX_FILE_BYTES:
            raise GraphTransferError('GRAPH_DOWNLOAD_LIMIT_INVALID')
        if type(timeout) is not int or not (1 <= timeout <= 60):
            raise GraphTransferError('GRAPH_TIMEOUT_INVALID')
        self._get_token = token_provider
        self._hosts = frozenset(redirect_hosts)
        self._request = executor or _https_request
        self._sleep = sleeper
        self._timeout = timeout
        self._limit = max_file_bytes

    def _call(self, url: str, headers: dict[str, str], max_bytes: int) -> HttpResult:
        try:
            result = self._request(url, headers, max_bytes, self._timeout)
            if (not isinstance(result, HttpResult) or type(result.status) is not int
                or type(result.body) is not bytes or len(result.body) > max_bytes):
                raise GraphTransferError('GRAPH_HTTP_INVALID_RESPONSE')
            return result
        except GraphTransferError:
            raise
        except Exception:
            # Network and injected provider errors could contain token or URL.
            raise GraphTransferError('GRAPH_NETWORK_FAILED') from None

    def __call__(self, drive_id: str, item_id: str) -> tuple[bytes, str]:
        from urllib.parse import quote
        drive = quote(_identity(drive_id, 'DRIVE_ID'), safe='')
        item = quote(_identity(item_id, 'ITEM_ID'), safe='')
        url = f'https://{GRAPH_HOST}/v1.0/drives/{drive}/items/{item}/content'
        for attempt in range(MAX_RETRIES + 1):
            try:
                token = self._get_token()
            except Exception:
                raise GraphTransferError('GRAPH_AUTH_PROVIDER_FAILED') from None
            if not isinstance(token, str) or not token or len(token) > 16384 or any(c.isspace() for c in token):
                raise GraphTransferError('GRAPH_AUTH_TOKEN_INVALID')
            result = self._call(url, {'Authorization': f'Bearer {token}'}, self._limit)
            # No persistence/logging of token; drop reference promptly.
            token = None
            if result.status in RETRYABLE and attempt < MAX_RETRIES:
                raw_wait = result.header('retry-after')
                wait = min(int(raw_wait), MAX_RETRY_AFTER) if raw_wait.isdecimal() and len(raw_wait) <= 4 else 2 ** attempt
                self._sleep(wait)
                continue
            if result.status in (301, 303, 307, 308):
                raise GraphTransferError('GRAPH_UNEXPECTED_REDIRECT')
            if result.status == 302:
                _, signed_url = _location(result.header('location'), set(self._hosts))
                cdn = self._call(signed_url, {}, self._limit)
                if cdn.status != 200:
                    raise GraphTransferError('GRAPH_CONTENT_HTTP_ERROR')
                result = cdn
            elif result.status != 200:
                raise GraphTransferError('GRAPH_CONTENT_HTTP_ERROR')
            if not result.body:
                raise GraphTransferError('GRAPH_BINARY_EMPTY')
            mime = result.header('content-type').split(';', 1)[0].strip().lower()
            if not mime:
                raise GraphTransferError('GRAPH_CONTENT_TYPE_MISSING')
            return result.body, mime
        raise GraphTransferError('GRAPH_RETRY_EXHAUSTED')
