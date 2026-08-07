"""
Sharing API client.
"""

import json
import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Optional, Union
from urllib.parse import parse_qs, urlparse, urlunparse

import httpx

from . import _util, _version
from .errors import (
    AuthError,
    ConfigError,
    Error,
    InvalidTokenError,
    NetworkError,
    Retry,
    ServerError,
    TimeoutError,
)

logger = logging.getLogger(__name__)


class Timeout:
    def __init__(self, timeout: Optional[float]):
        self._max_duration = timeout or 0
        self._start_ts = time.monotonic()

    def start(self) -> None:
        self._start_ts = time.monotonic()

    def stop(self) -> None:
        pass

    def check(self) -> None:
        if 0 < self._max_duration < time.monotonic() - self._start_ts:
            raise TimeoutError("Query timed out")


@dataclass
class Query:
    """Handle one 3-phase async query.

    Check for timeout every time client is accessed.
    """

    _client: httpx.Client
    timeout: Timeout

    # Query details for introspection
    post_url: Optional[httpx.URL] = None

    def __enter__(self) -> "Query":
        self._client.__enter__()
        self.timeout.start()
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> Any:
        self.timeout.stop()
        return self._client.__exit__(exc_type, exc, tb)

    @property
    def client(self) -> httpx.Client:
        self.timeout.check()
        return self._client


class _ApiClient:
    """Sharing API client."""

    # Allowed query parameters
    allowed_params = {
        "filter",
        "projection",
        "limit",
        "token",
        "start",
        "end",
        "sort",
        "reverse",
    }

    def __init__(
        self,
        url: str,
        *,
        user_agent: Optional[str] = None,
        allow_insecure: bool = False,
        transport: Optional[httpx.BaseTransport] = None,
        sleep_before_first_status_query: float = 0.5,
        sleep_after_50x_error_within_query: float = 10,
    ):
        self.urls = _ShareUrls(url, allow_insecure=allow_insecure)
        self.user_agent = user_agent or _version.user_agent

        # Transport to use in httpx client. Should only be defined in testing
        self.transport = transport
        # Time to wait for before first GET status after POST query
        self.sleep_before_first_status_query = sleep_before_first_status_query
        # Time to wait after 50x response within a query. These are typically
        # transitory errors on the server side
        self.sleep_after_50x_error_within_query = sleep_after_50x_error_within_query

    def _get_client(self) -> httpx.Client:
        """Initiaze new client."""
        return httpx.Client(
            base_url=self.urls.base_url,
            follow_redirects=True,
            timeout=60,
            headers={
                **self.urls.authorization_header,
                "USER-AGENT": self.user_agent,
                "ACCEPT-ENCODING": "gzip",
                "ACCEPT": "application/json",
            },
            transport=self.transport,
        )

    def _init_query(self, timeout: Optional[float]) -> Query:
        return Query(
            self._get_client(),
            Timeout(timeout),
        )

    def async_query(
        self,
        params: Optional[dict[str, Union[str, Sequence[str], int, float]]] = None,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        """Execute 3-phase async query."""
        qp = {**self.urls.qp, **(params or {})}
        invalid_params = qp.keys() - self.allowed_params
        if invalid_params:
            raise ConfigError(f"Invalid query parameters: {invalid_params}")

        with self._init_query(timeout) as query:
            status_url = self._async_post_query(query, qp)
            time.sleep(self.sleep_before_first_status_query)
            result_url = self._async_get_result_url(query, status_url)
            return self._async_get_result_response(query, result_url)

    def _async_post_query(
        self,
        query: Query,
        params: Optional[dict[str, Union[str, Sequence[str], int, float]]] = None,
    ) -> str:
        """POST async query.

        Returns status url.
        """
        try:
            response = query.client.post(url=self.urls.async_path, params=params)
            query.post_url = response.request.url
        except httpx.RequestError as error:
            raise NetworkError(
                f"Downloading {error.request.url} failed: {error}",
                url=str(error.request.url),
            )

        if self._server_unavailable(response.status_code):
            logger.debug(
                f"Error posting job, retry later ({response.status_code} {response.text})"
            )
            # Server error on initial post -> suggest retrying whole query later again
            raise Retry(
                after=response.headers.get("Retry-After", 10), url=str(response.url)
            )
        elif (invalid_inputs := self._invalid_input_error(response)) is not None:
            raise ConfigError(invalid_inputs, url=str(response.url))
        elif response.status_code == 500:
            raise ServerError(
                f"Sharing API server error 500 for submit, {response.text}",
                url=str(response.url),
            )
        elif response.status_code != 202:
            self._raise_for_client_error(response, "submit")
            raise NetworkError(
                f"Unexpected status {response.status_code} for submit, {response.text}",
                url=str(response.request.url),
            )

        try:
            return response.headers["Location"]
        except KeyError:
            raise Error("Location header missing from response", url=str(response.url))

    def _async_get_result_url(self, query: Query, url: str) -> str:
        """GET async result url from status url."""
        while True:
            try:
                response = query.client.get(url=url, follow_redirects=False)
            except httpx.RequestError as error:
                raise NetworkError(
                    f"Downloading {error.request.url} failed: {error}",
                    url=str(error.request.url),
                )

            if response.status_code == 302:
                # results are ready
                break
            elif response.status_code == 202:
                time.sleep(
                    _util.retry_after_delay(response.headers.get("Retry-After"), 1)
                )
            elif response.status_code == 500:
                raise ServerError(
                    f"Sharing API server error 500 getting status, {response.text}",
                    url=str(response.url),
                )
            elif self._server_unavailable(response.status_code):
                logger.debug(
                    f"Error getting status, try again after {self.sleep_after_50x_error_within_query} secs ({response.status_code} {response.text})"
                )
                time.sleep(self.sleep_after_50x_error_within_query)
            elif response.status_code == 410:
                if response.headers.get("X-STATUS") == "Job expired":
                    raise Error("The query has expired", url=str(response.url))
                else:
                    raise Retry(
                        "Job no longer exists (may have become stale)",
                        url=str(response.url),
                    )
            else:
                self._raise_for_client_error(response, "loading results")
                raise Retry(
                    f"Unexpected status {response.status_code} loading results, {response.text}",
                    url=str(response.url),
                )

        try:
            return response.headers["Location"]
        except KeyError:
            raise Error("Location header missing from response", url=str(response.url))

    def _async_get_result_response(self, query: Query, url: str) -> httpx.Response:
        """GET async result response."""
        while True:
            try:
                response = query.client.get(url)
            except httpx.RequestError as error:
                raise NetworkError(
                    f"Downloading {error.request.url} failed: {error}",
                    url=str(error.request.url),
                )

            if response.status_code == 200:
                break
            elif response.status_code == 410:
                if response.headers.get("X-STATUS") == "Job expired":
                    raise Error("The query has expired", url=str(response.url))
                else:
                    raise Retry(
                        "Results have been fetched already", url=str(response.url)
                    )
            elif response.status_code == 500:
                raise ServerError(
                    f"Sharing API server error 500 fetching results, {response.text}",
                    url=str(response.url),
                )
            elif self._server_unavailable(response.status_code):
                # sleep only 1 sec since results are stored only for a limited time
                logger.debug(
                    f"Error getting results, try again after {self.sleep_after_50x_error_within_query} secs ({response.status_code} {response.text})"
                )
                time.sleep(self.sleep_after_50x_error_within_query)
            elif self._is_invalid_token_error(response):
                assert query.post_url is not None  # for mypy
                raise InvalidTokenError(
                    query.post_url.params.get("token"), url=str(response.url)
                )
            else:
                self._raise_for_client_error(response, "fetching results")
                raise Retry(
                    f"Unexpected status {response.status_code} fetching results, {response.text}",
                    url=str(response.url),
                )

        return response

    @staticmethod
    def _raise_for_client_error(response: httpx.Response, phase: str) -> None:
        """Raise for a 4xx that will not become successful by retrying.

        Authentication and authorization failures used to surface as a generic
        NetworkError ("unexpected status"), which is misleading for what is the
        single most common user error: a wrong, expired or revoked api key.
        Likewise a permanent 4xx inside the polling loops used to be reported as
        a transient `Retry`.
        """
        status = response.status_code
        body = _util.truncate(response.text)

        if status in (401, 403):
            raise AuthError(
                f"Sharing API rejected the api key ({status}) for {phase}, {body}",
                url=str(response.url),
            )
        elif status == 404:
            raise ConfigError(
                f"Sharing API share not found (404) for {phase}, {body}",
                url=str(response.url),
            )
        elif status == 429:
            raise Retry(
                f"Sharing API rate limit exceeded (429) for {phase}, {body}",
                after=response.headers.get("Retry-After", 10),
                url=str(response.url),
            )
        elif 400 <= status < 500:
            # Permanent client error, retrying the identical request is futile
            raise ConfigError(
                f"Unexpected status {status} for {phase}, {body}",
                url=str(response.url),
            )

    @staticmethod
    def _server_unavailable(status: int) -> bool:
        """Does status mean server is unavailable?

        502 / 503 / 504 typically overloaded system. All of these should be
        transient on a valid hub url.
        """
        return status in (502, 503, 504)

    @staticmethod
    def _is_invalid_token_error(response: httpx.Response) -> bool:
        """Does response contain "invalid token" error.

        {"title": "400 Bad Request", "errors": [{"type": "storage", "key": "token", "message": "Invalid token: foo"}]}%
        """
        if response.status_code != 400:
            return False

        try:
            for error in response.json().get("errors", ()):
                if error.get("key") == "token" and error.get("message", "").startswith(
                    "Invalid token"
                ):
                    return True
        except json.decoder.JSONDecodeError:
            return False

        return False

    @staticmethod
    def _invalid_input_error(response: httpx.Response) -> Optional[Any]:
        """If response contains "invalid inputs" error, return it.

        {'title': '400 Invalid input(s)', 'description': '2 invalid input(s)', 'errors': [{'key': 'start', 'type': 'query validation', 'message': "Invalid start: ['foo']"}, {'key': 'startt', 'type': 'query validation', 'message': 'Unknown parameter: startt'}]}
        """
        if response.status_code != 400:
            return None

        try:
            d = response.json()
            if d.get("title") == "400 Invalid input(s)":
                return d.get("errors", [])
        except json.decoder.JSONDecodeError:
            return None

        return None


@dataclass
class _ShareUrls:
    """Share url handling."""

    base_url: str
    sync_path: str
    async_path: str
    # Never include the credential in repr(); see __repr__ of the dataclass.
    authorization_header: dict[str, str] = field(repr=False)
    qp: dict[str, list[str]]

    def __init__(self, sync_url: str, *, allow_insecure: bool = False):
        """Build urls from a sync url.

        The provided sync url must be an `https` url, since the api key is sent
        to the server on every request. `allow_insecure` opts out of that check
        for e.g. development servers, and sends the api key in cleartext.

        The provided sync url must have apikey query parameter, which will be
        separated from the url and used in the Authorization header on async api
        queries. All the query parameters are parsed and saved in `qp`, this is
        to allow merging them with the parameters provided in the url.
        (by default httpx overrides qp's in url)

        The api key is never included in `repr()` or `str()` of this object, so
        that it does not leak into logs, tracebacks or error reporting tools.

        >>> _ShareUrls("https://example.com/shares/v2/share-id?apikey=api-key&filter=foo=bar")
        _ShareUrls(base_url='https://example.com', sync_path='/shares/v2/share-id', async_path='/shares/v2/async/share-id', qp={'filter': ['foo=bar']})
        >>> str(_ShareUrls("https://example.com/shares/v2/share-id?apikey=api-key&filter=foo=bar"))
        'https://example.com//shares/v2/async/share-id'
        >>> _ShareUrls("https://example.com/shares/v2/share-id?filter=foo=bar")
        Traceback (most recent call last):
        arcticsecurity.sharing_api.errors.ConfigError: API share url must have apikey parameter
        >>> _ShareUrls("http://example.com/shares/v2/share-id?apikey=api-key")
        Traceback (most recent call last):
        arcticsecurity.sharing_api.errors.ConfigError: API share url must use https, not 'http' (pass allow_insecure=True to override)
        """
        o = urlparse(sync_url)

        if o.scheme != "https" and not (allow_insecure and o.scheme == "http"):
            raise ConfigError(
                f"API share url must use https, not {o.scheme!r}"
                " (pass allow_insecure=True to override)"
            )

        if not o.netloc:
            raise ConfigError(f"API share url has no host: {sync_url!r}")

        qp = parse_qs(o.query, keep_blank_values=True)

        if "apikey" not in qp:
            raise ConfigError("API share url must have apikey parameter")
        elif len(qp["apikey"]) > 1:
            raise ConfigError("API share url must have exactly one apikey parameter")

        self.base_url = urlunparse(o._replace(path="", query=""))
        self.sync_path = o.path
        self.async_path = re.sub(r"^/shares(/v2)?", "/shares/v2/async", o.path)
        self.authorization_header = {"Authorization": f"token {qp.pop('apikey')[0]}"}
        self.qp = qp

    def __str__(self) -> str:
        return f"{self.base_url}/{self.async_path}"
