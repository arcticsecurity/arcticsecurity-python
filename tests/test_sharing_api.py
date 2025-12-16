"""
Test sharing api library.
"""

from datetime import datetime, timezone
from itertools import chain
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest

from arcticsecurity import sharing_api
from arcticsecurity.sharing_api._api_client import _ApiClient

# should be ok for these tests for last_inserted_token to be always the same
# (if not, change)
last_inserted_token = str(uuid4())


class MockClient(_ApiClient):
    def __init__(self, url, events=[()], tokens=()):
        super().__init__(url)
        self.events_iterator = iter(events)
        self.token_iterator = iter(tokens)

    def async_query(self, *args, **kwargs):
        headers = {"x-last-inserted-token": last_inserted_token}

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

        with pytest.raises(sharing_api.ConfigError):
            sharing_api.Query(url)

    def test_sort_not_allowed_in_url(self):
        """Test explicitly that `sort` is not allowed in url."""
        sid = "share-id"
        url = f"https://example.com/shares/v2/{sid}?apikey=api-key&sort=key"

        with pytest.raises(sharing_api.ConfigError):
            sharing_api.Query(url)

    def test_apikey_missing_from_url(self):
        """Test apikey missing from url raises error on init."""
        sid = "share-id"
        url = f"https://example.com/shares/v2/{sid}?foo=bar"

        with pytest.raises(sharing_api.ConfigError):
            sharing_api.Query(url)

    def test_ctor_arg_validation(self):
        """Test ctor args are validated."""
        with pytest.raises(TypeError):
            sharing_api.Query(1)

        with pytest.raises(TypeError):
            sharing_api.Query(None)

        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        with pytest.raises(TypeError):
            sharing_api.Query(url, user_agent=1)

        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        with pytest.raises(ValueError):
            sharing_api.Query(url, foo=None)

    def test_query_arg_validation(self):
        """Test query args are validated."""
        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        query = sharing_api.Query(url)

        with pytest.raises(TypeError):
            next(query.query(filter=1))

        with pytest.raises(TypeError):
            next(query.query(projection="feed"))

        with pytest.raises(TypeError):
            next(query.query(start="2025-01-01"))

        with pytest.raises(TypeError):
            next(query.query(end="2025-01-01"))

        with pytest.raises(TypeError):
            next(query.query(reverse=1))

        with pytest.raises(TypeError):
            next(query.query(max_events=None))

        with pytest.raises(TypeError):
            next(query.query(timeout="100"))


class TestSync:
    def test_empty(self):
        """Test fetching no events succeeds."""
        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        events = ()
        sync = sharing_api.Sync(url)
        client = MockClient(url, events=events)
        sync.api_client = client

        rx_events, token = sync.read()
        assert rx_events == []
        assert token == last_inserted_token

    def test_one_event(self):
        """Test fetching one event from one page succeeds."""
        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        events = ([{"foo": "bar", "uuid": str(uuid4())}],)
        sync = sharing_api.Sync(url)
        client = MockClient(url, events=events)
        sync.api_client = client

        rx_events, token = sync.read()
        assert rx_events == events[0]
        assert token == last_inserted_token

    def test_multiple_pages(self):
        """Test fetching multiple pages succeeds."""
        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        events = (
            [{"foo": "bar", "uuid": str(uuid4())}],
            [{"baz": "qux", "uuid": str(uuid4())}],
        )
        tokens = (str(uuid4()),)
        sync = sharing_api.Sync(url)
        client = MockClient(url, events=events, tokens=tokens)
        sync.api_client = client

        rx_events, token = sync.read()
        assert rx_events == events[0]
        assert token == tokens[0]

        rx_events, token = sync.read(token=token)
        assert rx_events == events[1]
        assert token == last_inserted_token

        rx_events, token = sync.read(token=token)
        assert rx_events == []
        assert token == last_inserted_token

    def test_pagesize(self):
        pagesize = 100

        class Client(MockClient):
            def async_query(self, params, timeout):
                assert params["limit"] == pagesize
                return httpx.Response(200, json=[])

        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        sync = sharing_api.Sync(url)
        client = Client(url)
        sync.api_client = client
        sync.read(pagesize=pagesize)

    def test_start_passed_if_token_none(self):
        dt = datetime(2025, 1, 1, tzinfo=timezone.utc)

        class Client(MockClient):
            def async_query(self, params, timeout):
                assert params["start"] == dt.timestamp()
                assert "token" not in params
                return httpx.Response(200, json=[])

        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        sync = sharing_api.Sync(url, start=dt)
        client = Client(url)
        sync.api_client = client
        sync.read()

    def test_start_not_passed_if_token_present(self):
        dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
        token = "foo"

        class Client(MockClient):
            def async_query(self, params, timeout):
                assert params["token"] == token
                assert "start" not in params
                return httpx.Response(200, json=[])

        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        sync = sharing_api.Sync(url, start=dt)
        client = Client(url)
        sync.api_client = client
        sync.read(token=token)

    def test_start_set_by_seek_passed(self):
        dt = datetime(2025, 1, 1, tzinfo=timezone.utc)

        class Client(MockClient):
            def async_query(self, params, timeout):
                assert params["start"] == dt.timestamp()
                assert "token" not in params
                return httpx.Response(200, json=[])

        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        sync = sharing_api.Sync(url)
        sync.seek(dt)
        client = Client(url)
        sync.api_client = client
        sync.read()

    def test_start_naive_datetime(self, monkeypatch):
        system_tz = "Europe/London"
        monkeypatch.setenv("TZ", system_tz)
        import time

        if hasattr(time, "tzset"):
            time.tzset()

        naive_dt = datetime(2025, 1, 1)
        aware_dt = naive_dt.replace(tzinfo=ZoneInfo(system_tz))

        class Client(MockClient):
            def async_query(self, params, timeout):
                # start is really on the local system timezone
                assert params["start"] == aware_dt.timestamp()
                return httpx.Response(200, json=[])

        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        sync = sharing_api.Sync(url, start=naive_dt)
        client = Client(url)
        sync.api_client = client
        sync.read()

    def test_start_aware_datetime(self, monkeypatch):
        system_tz = "Europe/London"
        tz = "Europe/Helsinki"
        monkeypatch.setenv("TZ", system_tz)
        import time

        if hasattr(time, "tzset"):
            time.tzset()

        aware_dt = datetime(2025, 1, 1, tzinfo=ZoneInfo(tz))

        class Client(MockClient):
            def async_query(self, params, timeout):
                # start is really on the local system timezone
                assert params["start"] == aware_dt.timestamp()
                return httpx.Response(200, json=[])

        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        sync = sharing_api.Sync(url, start=aware_dt)
        client = Client(url)
        sync.api_client = client
        sync.read()

    def test_start_numeric(self, monkeypatch):
        start = 100

        class Client(MockClient):
            def async_query(self, params, timeout):
                assert params["start"] == start
                return httpx.Response(200, json=[])

        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        sync = sharing_api.Sync(url, start=start)
        client = Client(url)
        sync.api_client = client
        sync.read()

    def test_start_none(self, monkeypatch):
        ts = 1234567890

        # Mock time.time() to return specified time
        import time

        monkeypatch.setattr(time, "time", lambda: ts)

        class Client(MockClient):
            def async_query(self, params, timeout):
                # start is really on the local system timezone
                assert params["start"] == ts
                return httpx.Response(200, json=[])

        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        sync = sharing_api.Sync(url)
        client = Client(url)
        sync.api_client = client
        sync.read()

    def test_ctor_arg_validation(self):
        """Test ctor args are validated."""
        url = "https://example.com/shares/v2/share-id?apikey=api-key"

        with pytest.raises(TypeError):
            sharing_api.Sync(1)

        with pytest.raises(TypeError):
            sharing_api.Sync(None)

        with pytest.raises(TypeError):
            sharing_api.Sync(url, filter=1)

        with pytest.raises(TypeError):
            sharing_api.Sync(url, projection="feed")

        with pytest.raises(TypeError):
            sharing_api.Sync(url, start="2025-01-01")

        with pytest.raises(TypeError):
            sharing_api.Sync(url, user_agent=1)

        with pytest.raises(ValueError):
            sharing_api.Sync(url, foo=None)

    def test_query_arg_validation(self):
        """Test query args are validated."""
        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        sync = sharing_api.Sync(url)

        with pytest.raises(TypeError):
            sync.read(token=1)

        with pytest.raises(TypeError):
            sync.read(pagesize=None)

        with pytest.raises(TypeError):
            sync.read(timeout="100")

    def test_seek_arg_validation(self):
        """Test seek args are validated."""
        url = "https://example.com/shares/v2/share-id?apikey=api-key"
        sync = sharing_api.Sync(url)

        with pytest.raises(TypeError):
            sync.seek("2025-01-01")
