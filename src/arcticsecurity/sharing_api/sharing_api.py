"""
Sharing API client.
"""

import logging
import time
from collections.abc import Iterable, Sequence, Set
from datetime import datetime
from typing import Any, Optional, Union

from ._api_client import _ApiClient
from .errors import ConfigError

logger = logging.getLogger(__name__)
Event = dict[str, Union[str, list[str]]]


class Sync:
    """Sync events from sharing API."""

    allowed_user_provided_qps = {
        "filter",
        "projection",
    }

    def __init__(
        self,
        url: str,
        *,
        filter: Optional[str] = None,
        projection: Optional[Sequence[str]] = None,
        start: Union[datetime, int, float, None] = None,
        **kwargs: Any,
    ):
        # Check args
        if not isinstance(url, str):
            raise TypeError(f"url must be string not {type(url)}")

        if not (filter is None or isinstance(filter, str)):
            raise TypeError(f"filter must be string or None, not {type(filter)}")

        if not (
            projection is None
            or isinstance(projection, (Sequence, Set))
            and all(isinstance(x, str) for x in projection)
        ):
            raise TypeError(
                "projection must be a list of key names, each an instance of str"
            )

        user_agent = kwargs.pop("user_agent", None)
        if not (user_agent is None or isinstance(user_agent, str)):
            raise TypeError(
                f"user_agent must be string or None, not {type(user_agent)}"
            )

        if kwargs:
            raise ValueError(f"Unknown parameter(s) {tuple(kwargs.keys())}")

        # Initialize client
        self.api_client = _ApiClient(url, user_agent=user_agent)

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
    ) -> tuple[list[Event], Optional[str]]:
        """Sync events from sharing API

        Events are returned sorted by insertion time.
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
        except KeyError:
            token = resp.headers.get("x-last-inserted-token", None)

        return resp.json(), token

    def seek(self, ts: Union[datetime, int, float, None]) -> None:
        """Set sync start to specific time."""
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

    def __init__(self, url: str, **kwargs: Any):
        # Check args
        if not isinstance(url, str):
            raise TypeError(f"url must be string not {type(url)}")

        user_agent = kwargs.pop("user_agent", None)
        if not (user_agent is None or isinstance(user_agent, str)):
            raise TypeError(
                f"user_agent must be string or None, not {type(user_agent)}"
            )

        if kwargs:
            raise ValueError(f"Unknown parameter(s) {tuple(kwargs.keys())}")

        # Initialize client
        self.api_client = _ApiClient(url, user_agent=user_agent)

        invalid_qps_in_url = (
            self.api_client.urls.qp.keys() - self.allowed_user_provided_qps
        )
        if invalid_qps_in_url:
            raise ConfigError(f"Invalid qps in url: {invalid_qps_in_url}")

    def query(
        self,
        *,
        filter: Optional[str] = None,
        projection: Optional[Sequence[str]] = None,
        start: Union[datetime, int, float, None] = None,
        end: Union[datetime, int, float, None] = None,
        reverse: bool = False,
        max_events: int = 0,
        timeout: Optional[float] = 600,
        **kwargs: Any,
    ) -> Iterable[Event]:
        """Query sharing API.

        Events are returned sorted by timestamp.
        """
        if not (filter is None or isinstance(filter, str)):
            raise TypeError(f"filter must be string or None, not {type(filter)}")

        if not (
            projection is None
            or isinstance(projection, (Sequence, Set))
            and all(isinstance(x, str) for x in projection)
        ):
            raise TypeError(
                "projection must be a list of key names, each an instance of str"
            )

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

        more = True
        token = None
        n_events = 0

        while more:
            resp = self.api_client.async_query(qp, timeout=timeout)
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
                if 0 < max_events <= n_events:
                    more = False
                    break


def query(url: str, **kwargs: Any) -> Iterable[Event]:
    """Shortcut to Query().query()."""
    return Query(url).query(**kwargs)


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
