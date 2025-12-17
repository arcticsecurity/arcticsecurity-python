"""
Sharing API client.
"""

import json
import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Optional, Union
from urllib.parse import parse_qs, urlparse, urlunparse

import httpx

from . import _version
from .errors import (
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
        transport: Optional[httpx.BaseTransport] = None,
        sleep_before_first_status_query: float = 0.5,
        sleep_after_50x_error_within_query: float = 10,
    ):
        self.urls = _ShareUrls(url)
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
            raise NetworkError(f"Downloading {error.request.url} failed: {error}")

        if self._server_unavailable(response.status_code):
            logger.debug(
                f"Error posting job, retry later ({response.status_code} {response.text})"
            )
            # Server error on initial post -> suggest retrying whole query later again
            raise Retry(after=response.headers.get("Retry-After", 10))
        elif (invalid_inputs := self._invalid_input_error(response)) is not None:
            raise ConfigError(invalid_inputs)
        elif response.status_code == 500:
            raise ServerError(
                f"Sharing API server error 500 for submit, {response.text}"
            )
        elif response.status_code != 202:
            raise NetworkError(
                f"Unexpected status {response.status_code} for submit, {response.text}"
            )

        try:
            return response.headers["Location"]
        except KeyError:
            raise Error("Location header missing from response")

    def _async_get_result_url(self, query: Query, url: str) -> str:
        """GET async result url from status url."""
        while True:
            try:
                response = query.client.get(url=url, follow_redirects=False)
            except httpx.RequestError as error:
                raise NetworkError(f"Downloading {error.request.url} failed: {error}")

            if response.status_code == 302:
                # results are ready
                break
            elif response.status_code == 202:
                time.sleep(int(response.headers.get("Retry-After", 1)))
            elif response.status_code == 500:
                raise ServerError(
                    f"Sharing API server error 500 getting status, {response.text}"
                )
            elif self._server_unavailable(response.status_code):
                logger.debug(
                    f"Error getting status, try again after {self.sleep_after_50x_error_within_query} secs ({response.status_code} {response.text})"
                )
                time.sleep(self.sleep_after_50x_error_within_query)
            else:
                raise Retry(
                    f"Unexpected status {response.status_code} loading results, {response.text}"
                )

        try:
            return response.headers["Location"]
        except KeyError:
            raise Error("Location header missing from response")

    def _async_get_result_response(self, query: Query, url: str) -> httpx.Response:
        """GET async result response."""
        while True:
            try:
                response = query.client.get(url)
            except httpx.RequestError as error:
                raise NetworkError(f"Downloading {error.request.url} failed: {error}")

            if response.status_code == 200:
                break
            elif response.status_code == 410:
                raise Retry("Results have been fetched already")
            elif response.status_code == 500:
                raise ServerError(
                    f"Sharing API server error 500 fetching results, {response.text}"
                )
            elif self._server_unavailable(response.status_code):
                # sleep only 1 sec since results are stored only for a limited time
                logger.debug(
                    f"Error getting results, try again after {self.sleep_after_50x_error_within_query} secs ({response.status_code} {response.text})"
                )
                time.sleep(self.sleep_after_50x_error_within_query)
            elif self._is_invalid_token_error(response):
                assert query.post_url is not None  # for mypy
                raise InvalidTokenError(query.post_url.params.get("token"))
            else:
                raise Retry(
                    f"Unexpected status {response.status_code} fetching results, {response.text}"
                )

        return response

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
    authorization_header: dict[str, str]
    qp: dict[str, list[str]]

    def __init__(self, sync_url: str):
        """Build urls from a sync url.

        The provided sync url must have apikey query parameter, which will be
        separated from the url and used in the Authorization header on async api
        queries. All the query parameters are parsed and saved in `qp`, this is
        to allow merging them with the parameters provided in the url.
        (by default httpx overrides qp's in url)

        >>> _ShareUrls("https://example.com/shares/v2/share-id?apikey=api-key&filter=foo=bar")
        _ShareUrls(base_url='https://example.com', sync_path='/shares/v2/share-id', async_path='/shares/v2/async/share-id', authorization_header={'Authorization': 'token api-key'}, qp={'filter': ['foo=bar']})
        >>> _ShareUrls("https://example.com/shares/v2/share-id?filter=foo=bar")
        Traceback (most recent call last):
        arcticsecurity.sharing_api.errors.ConfigError: API share url must have apikey parameter
        """
        o = urlparse(sync_url)
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
