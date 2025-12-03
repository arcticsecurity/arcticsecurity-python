"""
TODO:
    - user-defined timeout
      - for query() or one phase?
    - start, end, support datetime / int
    - error handling, retries?
"""

import logging
import time
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any, Optional, Union

from ._api_client import _ApiClient
from .errors import QueryError

logger = logging.getLogger(__name__)
Event = dict[str, Union[str, list[str]]]


class Sync:
    """Sync events from sharing API."""

    # Allowed query parameters
    allowed_user_provided_qps = {
        "filter",
        "projection",
        "limit",
        "token",
    }

    def __init__(self, url: str):
        self.api_client = _ApiClient(url)

        invalid_qps_in_url = (
            self.api_client.urls.qp.keys() - self.allowed_user_provided_qps
        )
        if invalid_qps_in_url:
            raise QueryError(f"Invalid qps in url: {invalid_qps_in_url}")

    def read(
        self,
        *,
        filter: Optional[str] = None,
        projection: Optional[Sequence[str]] = None,
        token: Optional[str] = None,
        pagesize: int = 1000,
    ) -> tuple[list[Event], Optional[str]]:
        """Sync events from sharing API

        Events are returned sorted by insertion time.
        """
        qp = _remove_none_values(
            {
                "filter": filter,
                "projection": projection,
                "token": token,
                "limit": pagesize if pagesize != 0 else None,
                "sort": "_id",
            }
        )

        # If token is missing, default to current time
        if "token" not in qp:
            qp["start"] = time.time()

        resp = self.api_client.async_query(qp)

        try:
            token = resp.headers["x-next-token"]
        except KeyError:
            token = resp.headers["x-last-inserted-token"]

        return resp.json(), token


class Query:
    """Query events from sharing API."""

    # Allowed query parameters
    allowed_user_provided_qps = {
        "filter",
        "projection",
        "limit",
        "start",
        "end",
        "reverse",
    }

    def __init__(self, url: str):
        self.api_client = _ApiClient(url)

        invalid_qps_in_url = (
            self.api_client.urls.qp.keys() - self.allowed_user_provided_qps
        )
        if invalid_qps_in_url:
            raise QueryError(f"Invalid qps in url: {invalid_qps_in_url}")

    def query(
        self,
        *,
        filter: Optional[str] = None,
        projection: Optional[Sequence[str]] = None,
        start: Union[datetime, int, float, None] = None,
        end: Union[datetime, int, float, None] = None,
        reverse: bool = False,
        max_events: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterable[Event]:
        """Query sharing API.

        Events are returned sorted by timestamp.
        """
        qp = _remove_none_values(
            {
                "filter": filter,
                "projection": projection,
                "start": _build_start_end(start),
                "end": _build_start_end(end),
                "reverse": "" if reverse else None,
                "limit": kwargs.get("pagesize", 1000),
            }
        )

        more = True
        token = None
        n_events = 0

        while more:
            resp = self.api_client.async_query(qp)
            events = resp.json()
            logger.debug(f"queried, got {len(events)} events")

            try:
                token = resp.headers["x-next-token"]
            except KeyError:
                more = False
            else:
                qp["token"] = token
                more = True

            for event in events:
                yield event
                n_events += 1
                if max_events and n_events == max_events:
                    more = False
                    break


def query(url: str, **kwargs: Any) -> Iterable[Event]:
    """Shortcut to Query().query()."""
    return Query(url).query(**kwargs)


def _remove_none_values(d: dict[str, Optional[Any]]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def _build_start_end(t: Union[datetime, int, float, None]) -> Union[int, float, None]:
    """Build start / end query parameter."""
    if t is None:
        return None
    elif isinstance(t, (int, float)):
        return t
    else:
        return t.timestamp()
