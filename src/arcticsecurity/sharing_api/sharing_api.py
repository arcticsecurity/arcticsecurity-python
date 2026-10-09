"""
Sharing API client.
"""

import logging
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Union

import requests

from . import _util
from ._api_client import _ApiClient
from .errors import ConfigError, ServerError

logger = logging.getLogger(__name__)

Event = dict[str, Union[str, list[str]]]
"""A single event, mapping a field name to its value or list of values."""


@dataclass(frozen=True)
class SyncReadResponse:
    """Result of a single `Sync.read()` call.

    Attributes:
        events: The batch of events, in database insertion order.
        token: Continuation token to pass to the next `read()` call. This is
            the next token when more events are available, and the last
            inserted token otherwise. It is `None` only when the server
            reported no position at all, in which case the previously held
            token should be kept.
        has_more: Whether more events already exist in the database at the
            moment. When `False`, the caller has reached the end of the
            stream and should wait before reading again.
    """

    events: list[Event]
    token: Optional[str]
    has_more: bool


class Sync:
    """Synchronize events from sharing API.

    Reads every event matching the given conditions in database insertion
    order, so that a caller can keep its own copy of the events up to date
    without missing any.

    The name refers to that synchronization, not to the sharing API's
    synchronous endpoints. This class queries the asynchronous endpoints,
    as `Query` does.
    """

    allowed_user_provided_qps = {
        "filter",
        "projection",
    }

    def __init__(
        self,
        url: str,
        *,
        filter: Optional[str] = None,
        projection: Optional[Iterable[str]] = None,
        start: Union[datetime, int, float, None] = None,
        user_agent: Optional[str] = None,
        allow_insecure: bool = False,
        **kwargs: Any,
    ):
        """
        Initialize Sync class.

        Args:
            url: Sharing API url, must be an `https` url and must include
                `apikey` query parameter.
            filter: Rulelang filter.
            projection: List of event field names to include in the results. Note that the list of keys provided by the server can only be limited by this parameter.
            start: Start time for the initial query. Can also be set with seek(). Default value `None` means current time. Positive numbers are interpret as epoch time. Non-positive numbers are interpret as that many seconds in the past.
            user_agent: Value appended to the `User-Agent` request header.
            allow_insecure: Accept a plain `http` url. The api key is sent on every request, so it is then transmitted in cleartext. Intended for development servers only.
        """

        # Check args
        if not isinstance(url, str):
            raise TypeError(f"url must be string not {type(url)}")

        if not (filter is None or isinstance(filter, str)):
            raise TypeError(f"filter must be string or None, not {type(filter)}")

        projection = _validate_projection(projection)

        client_kwargs = _validate_client_kwargs(user_agent, allow_insecure)

        if kwargs:
            raise ValueError(f"Unknown parameter(s) {tuple(kwargs.keys())}")

        # Initialize client
        self.api_client = _ApiClient(url, **client_kwargs)

        invalid_qps_in_url = (
            self.api_client.urls.qp.keys() - self.allowed_user_provided_qps
        )
        if invalid_qps_in_url:
            raise ConfigError(f"Invalid qps in url: {invalid_qps_in_url}")

        self.qp = {
            "filter": filter,
            "projection": projection,
            "sort": "_id",
        }

        self.start = self._seek(start)

    def read(
        self,
        *,
        token: Optional[str] = None,
        pagesize: int = 1000,
        timeout: Optional[float] = 600,
    ) -> SyncReadResponse:
        """Read the next batch of events to synchronize.

        Events are returned sorted by insertion time.

        Args:
            token: Continuation token. If not given, the start time set earlier is used.
            pagesize: Maximum number of events to return.
            timeout: Timeout for the operation in [s].

        Returns:
            Batch of events and a continuation token for the next query.
        """
        if not (token is None or isinstance(token, str)):
            raise TypeError(f"token must be string or None, not {type(token)}")

        if not isinstance(pagesize, int):
            raise TypeError(f"pagesize must be int not {type(pagesize)}")

        if not (timeout is None or isinstance(timeout, (int, float))):
            raise TypeError(f"timeout must be float or None, not {type(timeout)}")

        qp = _remove_none_values(
            {
                **self.qp,
                **{
                    "token": token,
                    "limit": pagesize if pagesize != 0 else None,
                },
            }
        )

        if "token" not in qp:
            qp["start"] = self.start

        resp = self.api_client.async_query(qp, timeout=timeout)

        try:
            token = resp.headers["x-next-token"]
            has_more = True
        except KeyError:
            token = resp.headers.get("x-last-inserted-token", None)
            has_more = False

        return SyncReadResponse(
            _parse_events(resp),
            token,
            has_more,
        )

    def seek(self, ts: Union[datetime, int, float, None]) -> None:
        """Set sync start to specific time.

        Args:
            ts: See start in __init__.
        """
        self.start = self._seek(ts)

    def _seek(self, ts: Union[datetime, int, float, None]) -> float:
        """Set sync start to specific time."""
        if not (ts is None or isinstance(ts, (int, float, datetime))):
            raise TypeError(f"ts must be int, float, datetime or None, not {type(ts)}")

        if ts is None:
            return time.time()
        elif isinstance(ts, (int, float)):
            return float(ts)
        else:
            return ts.timestamp()

    def __str__(self) -> str:
        return f"Sync({self.api_client.urls})"


class Query:
    """Query events from sharing API."""

    allowed_user_provided_qps = {
        "filter",
        "projection",
        "limit",
        "start",
        "end",
        "reverse",
    }

    def __init__(
        self,
        url: str,
        *,
        user_agent: Optional[str] = None,
        allow_insecure: bool = False,
        **kwargs: Any,
    ):
        """
        Initialize Query class.

        Args:
            url: Sharing API url, must be an `https` url and must include
                `apikey` query parameter.
            user_agent: Value appended to the `User-Agent` request header.
            allow_insecure: Accept a plain `http` url. The api key is sent on every request, so it is then transmitted in cleartext. Intended for development servers only.
        """

        # Check args
        if not isinstance(url, str):
            raise TypeError(f"url must be string not {type(url)}")

        client_kwargs = _validate_client_kwargs(user_agent, allow_insecure)

        if kwargs:
            raise ValueError(f"Unknown parameter(s) {tuple(kwargs.keys())}")

        # Initialize client
        self.api_client = _ApiClient(url, **client_kwargs)

        invalid_qps_in_url = (
            self.api_client.urls.qp.keys() - self.allowed_user_provided_qps
        )
        if invalid_qps_in_url:
            raise ConfigError(f"Invalid qps in url: {invalid_qps_in_url}")

    def query(
        self,
        *,
        filter: Optional[str] = None,
        projection: Optional[Iterable[str]] = None,
        start: Union[datetime, int, float, None] = None,
        end: Union[datetime, int, float, None] = None,
        reverse: bool = False,
        max_events: int = 0,
        timeout: Optional[float] = 600,
        **kwargs: Any,
    ) -> Iterator[Event]:
        """Query sharing API.

        Events are returned sorted by timestamp.

        Args:
            filter: Rulelang filter.
            projection: List of event field names to include in the results. Note that the list of keys provided by the server can only be limited by this parameter.
            start: Start time for the query. Default value `None` means forever. Positive numbers are interpret as epoch time. Non-positive numbers are interpret as that many seconds in the past.
            end: End time for the query. Default value `None` means current time. Positive numbers are interpret as epoch time. Non-positive numbers are interpret as that many seconds in the past.
            reverse: Return events in reverse order.
            max_events: Maximum number of events to generate.
            timeout: Timeout for one sharing API query fetching more events in [s].

        Returns:
            Generator yielding events matching the query.
        """
        if not (filter is None or isinstance(filter, str)):
            raise TypeError(f"filter must be string or None, not {type(filter)}")

        projection = _validate_projection(projection)

        if not (start is None or isinstance(start, (int, float, datetime))):
            raise TypeError(
                f"start must be int, float, datetime or None, not {type(start)}"
            )

        if not (end is None or isinstance(end, (int, float, datetime))):
            raise TypeError(
                f"end must be int, float, datetime or None, not {type(end)}"
            )

        if not isinstance(reverse, bool):
            raise TypeError(f"reverse must be bool, not {type(bool)}")

        if not isinstance(max_events, int):
            raise TypeError(f"max_events must be int, not {type(max_events)}")

        if not (timeout is None or isinstance(timeout, (int, float))):
            raise TypeError(f"timeout must be float or None, not {type(timeout)}")

        pagesize = kwargs.pop("pagesize", 1000)
        if not isinstance(pagesize, int):
            raise TypeError(f"pagesize must be int, not {type(kwargs.get('pagesize'))}")

        if kwargs:
            raise ValueError(f"Unknown parameter(s) {tuple(kwargs.keys())}")

        qp = _remove_none_values(
            {
                "filter": filter,
                "projection": projection,
                "start": _build_start_end(start),
                "end": _build_start_end(end),
                "reverse": "" if reverse else None,
                "limit": pagesize,
            }
        )

        return self._iter_events(qp, max_events, timeout)

    def _iter_events(
        self,
        qp: dict[str, Any],
        max_events: int,
        timeout: Optional[float],
    ) -> Iterator[Event]:
        """Generate events page by page. Arguments are already validated."""
        more = True
        n_events = 0

        while more:
            resp = self.api_client.async_query(qp, timeout=timeout)
            events = _parse_events(resp)
            logger.debug(f"queried, got {len(events)} events")

            try:
                qp["token"] = resp.headers["x-next-token"]
            except KeyError:
                more = False
            else:
                more = True

            for event in events:
                yield event
                n_events += 1
                if 0 < max_events <= n_events:
                    more = False
                    break

    def __str__(self) -> str:
        return f"Query({self.api_client.urls})"


def query(url: str, **kwargs: Any) -> Iterable[Event]:
    """Shortcut to Query(url).query()."""
    return Query(url).query(**kwargs)


def _parse_events(resp: requests.Response) -> list[Event]:
    """Decode and sanity check an events response body.

    Query used to call resp.json() bare, so malformed output escaped as a raw
    json.JSONDecodeError instead of a ServerError. Neither caller checked that
    the payload was a list, so a JSON object made Query yield its keys as if
    they were events.
    """
    try:
        events = resp.json()
    except ValueError:
        logger.error(f"Invalid response from server {_util.truncate(resp.text)!r}")
        raise ServerError("Invalid response from server: not valid JSON")

    if not isinstance(events, list):
        logger.error(f"Unexpected response from server {_util.truncate(resp.text)!r}")
        raise ServerError(
            f"Unexpected response from server: expected a list of events,"
            f" got {type(events).__name__}"
        )

    return events


def _validate_projection(
    projection: Optional[Iterable[str]],
) -> Optional[list[str]]:
    """Validate and materialize the projection argument.

    Returning a list matters: validating with `all(... for x in projection)`
    exhausts a generator, and the exhausted object would then be handed to
    requests, which would serialize its repr() as the query parameter value.

    >>> _validate_projection(None) is None
    True
    >>> _validate_projection(x for x in ["uuid", "severity"])
    ['uuid', 'severity']
    >>> _validate_projection("uuid")
    Traceback (most recent call last):
    TypeError: projection must be a list of key names, each an instance of str
    """
    if projection is None:
        return None

    if isinstance(projection, str) or not isinstance(projection, Iterable):
        raise TypeError(
            "projection must be a list of key names, each an instance of str"
        )

    keys = list(projection)

    if not all(isinstance(x, str) for x in keys):
        raise TypeError(
            "projection must be a list of key names, each an instance of str"
        )

    return keys


def _validate_client_kwargs(
    user_agent: Optional[str], allow_insecure: bool
) -> dict[str, Any]:
    """Validate the api client arguments shared by Sync and Query."""
    if not (user_agent is None or isinstance(user_agent, str)):
        raise TypeError(f"user_agent must be string or None, not {type(user_agent)}")

    if not isinstance(allow_insecure, bool):
        raise TypeError(f"allow_insecure must be bool, not {type(allow_insecure)}")

    return {"user_agent": user_agent, "allow_insecure": allow_insecure}


def _remove_none_values(d: dict[str, Optional[Any]]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def _build_start_end(ts: Union[datetime, int, float, None]) -> Union[int, float, None]:
    """Build start / end query parameter."""
    if ts is None:
        return None
    elif isinstance(ts, (int, float)):
        return ts
    else:
        return ts.timestamp()
