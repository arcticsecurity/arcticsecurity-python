"""
TODO:
    - user-defined timeout
      - for query() or one phase?
    - start, end, support datetime / int
    - error handling, retries?
"""

import logging
from collections.abc import Iterable, Sequence
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
        "start",
        "end",
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
        projection: Optional[Union[str, Sequence[str]]] = None,
        token: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> tuple[list[Event], Optional[str]]:
        """Sync events from sharing API

        Events are returned sorted by insertion time.
        """
        qp = _remove_none_values(
            {
                "filter": filter,
                "projection": projection,
                "token": token,
                "start": start,
                "end": end,
                "limit": str(limit) if limit else None,
                "sort": "_id",
            }
        )

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
        projection: Optional[Union[str, Sequence[str]]] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        reverse: bool = False,
        max_events: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Iterable[Event]:
        """Query sharing API.

        Events are returned sorted by timestamp.
        """
        qp = _remove_none_values(
            {
                "filter": filter,
                "projection": projection,
                "start": start,
                "end": end,
                "reverse": "" if reverse else None,
                "limit": str(limit) if limit else None,
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
