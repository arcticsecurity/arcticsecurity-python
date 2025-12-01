"""
Test sharing api library.
"""

from itertools import chain
from uuid import uuid4

import httpx
import pytest

from arcticsecurity import sharing_api
from arcticsecurity.sharing_api._api_client import _ApiClient


class MockClient(_ApiClient):
    def __init__(self, url, events=[()], tokens=()):
        super().__init__(url)
        self.events_iterator = iter(events)
        self.token_iterator = iter(tokens)

    def async_query(self, *args, **kwargs):
        headers = {"x-last-inserted-token": str(uuid4())}

        next_token = next(self.token_iterator, None)
        if next_token:
            headers["x-next-token"] = next_token

        events = next(self.events_iterator, [])
        if events:
            headers["x-first-token"] = events[0]["uuid"]
            headers["x-last-token"] = events[-1]["uuid"]

        return httpx.Response(
            200,
            json=events,
            headers=headers,
        )


class TestQuery:
    def test_empty(self):
        """Test fetching no events succeeds."""
        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        events = ()
        query = sharing_api.Query(url)
        client = MockClient(url, events=events)
        query.api_client = client

        rx_events = list(query.query())
        assert rx_events == []

    def test_one_event(self):
        """Test fetching one event from one page succeeds."""
        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        events = ([{"foo": "bar", "uuid": str(uuid4())}],)
        query = sharing_api.Query(url)
        client = MockClient(url, events=events)
        query.api_client = client

        rx_events = list(query.query())
        assert rx_events == list(chain(*events))

    def test_multiple_pages(self):
        """Test fetching multiple pages succeeds."""
        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        events = (
            [{"foo": "bar", "uuid": str(uuid4())}],
            [{"baz": "qux", "uuid": str(uuid4())}],
        )
        tokens = (str(uuid4()),)
        query = sharing_api.Query(url)
        client = MockClient(url, events=events, tokens=tokens)
        query.api_client = client

        rx_events = list(query.query())
        assert rx_events == list(chain(*events))

    def test_max_events_one_page(self):
        """Test max_events limiting on one page."""
        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        events = (
            [{"foo": "bar", "uuid": str(uuid4())}],
            [{"baz": "qux", "uuid": str(uuid4())}],
        )
        tokens = (str(uuid4()),)
        query = sharing_api.Query(url)
        client = MockClient(url, events=events, tokens=tokens)
        query.api_client = client

        max_events = 1
        rx_events = list(query.query(max_events=max_events))
        assert rx_events == list(chain(*events))[0:max_events]

    def test_max_events_multiple_pages(self):
        """Test max_events limiting on multiple pages."""
        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        events = (
            [{"foo": "bar", "uuid": str(uuid4())}],
            [
                {"baz": "qux", "uuid": str(uuid4())},
                {"baa": "quu", "uuid": str(uuid4())},
            ],
        )
        tokens = (str(uuid4()),)
        query = sharing_api.Query(url)
        client = MockClient(url, events=events, tokens=tokens)
        query.api_client = client

        max_events = 2
        rx_events = list(query.query(max_events=max_events))
        assert rx_events == list(chain(*events))[0:max_events]

    def test_max_events_zero_means_unlimited(self):
        """Test max_events=0 means no limit."""
        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        events = (
            [{"foo": "bar", "uuid": str(uuid4())}],
            [{"baz": "qux", "uuid": str(uuid4())}],
        )
        tokens = (str(uuid4()),)
        query = sharing_api.Query(url)
        client = MockClient(url, events=events, tokens=tokens)
        query.api_client = client

        max_events = 0
        rx_events = list(query.query(max_events=max_events))
        assert rx_events == list(chain(*events))

    def test_unknown_query_param_in_url(self):
        """Test unknown qp in url raises error."""
        sid = "share-id"
        url = f"https://example.com/shares/v2/{sid}?apikey=api-key&foo=bar"

        with pytest.raises(sharing_api.QueryError):
            sharing_api.Query(url)

    def test_sort_not_allowed_in_url(self):
        """Test explicitly that `sort` is not allowed in url."""
        sid = "share-id"
        url = f"https://example.com/shares/v2/{sid}?apikey=api-key&sort=key"

        with pytest.raises(sharing_api.QueryError):
            sharing_api.Query(url)

    def test_apikey_missing_from_url(self):
        """Test apikey missing from url raises error on init."""
        sid = "share-id"
        url = f"https://example.com/shares/v2/{sid}?foo=bar"

        with pytest.raises(sharing_api.QueryError):
            sharing_api.Query(url)


class TestSync:
    pass
