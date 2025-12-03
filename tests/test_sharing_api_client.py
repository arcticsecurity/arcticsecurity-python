"""
Test API client.
"""

from itertools import chain
from uuid import uuid4

import httpx
import pytest

from arcticsecurity.sharing_api import _api_client, errors


class MockServer:
    """Mock sharing REST API."""

    def __init__(self, url: str, events=[()], tokens=()):
        self.urls = _api_client._ShareUrls(url)
        self.events = events
        self.jid = None
        self.rid = None

        self.events_iterator = iter(events)
        self.token_iterator = iter(tokens)

    def job_location(self):
        assert self.jid
        return f"{self.urls.async_path}/jobs/{self.jid}"

    def result_location(self):
        assert self.rid
        return f"{self.urls.async_path}/results/{self.rid}"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Route request to handler."""
        key = (request.method, request.url.path)

        if key == ("POST", self.urls.async_path):
            return self.handle_post_query(request)
        elif self.jid and key == ("GET", self.job_location()):
            return self.handle_get_status(request)
        elif self.rid and key == ("GET", self.result_location()):
            return self.handle_get_results(request)
        else:
            assert False, f"Unexpected query to REST API {key}"

    def handle_post_query(self, request):
        self.jid = str(uuid4())
        return httpx.Response(
            202,
            headers={"Location": self.job_location()},
        )

    def handle_get_status(self, request):
        self.jid = None
        self.rid = str(uuid4())
        return httpx.Response(
            302,
            headers={"Location": self.result_location()},
        )

    def handle_get_results(self, request):
        self.rid = None

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


class TestApi:
    """Test _Api."""

    def test_no_apikey_in_url(self):
        url = "https://example.com/shares/v2/share-id"
        with pytest.raises(errors.QueryError):
            _api_client._ApiClient(url)

    def test_many_apikeys_in_url(self):
        url = "https://example.com/shares/v2/share-id?apikey=k1&apikey=k2"
        with pytest.raises(errors.QueryError):
            _api_client._ApiClient(url)

    def test_invalid_qp_in_url(self):
        url = "https://example.com/shares/v2/share-id?apikey=k1&foo=bar"
        api = _api_client._ApiClient(url)
        with pytest.raises(errors.QueryError):
            api.async_query()

    def test_invalid_qp_in_arg(self):
        url = "https://example.com/shares/v2/share-id?apikey=k1"
        api = _api_client._ApiClient(url)
        with pytest.raises(errors.QueryError):
            api.async_query(params={"foo": "bar"})

    def test_post_fails_on_network_error(self):
        class Server(MockServer):
            def handle_post_query(self, request):
                raise httpx.RequestError("failed")

        url = "https://example.com/shares/v2/share-id?apikey=k1"
        xport = httpx.MockTransport(Server(url))
        api = _api_client._ApiClient(url, transport=xport)
        with pytest.raises(errors.NetworkError):
            api.async_query()

    def test_post_fails_on_401(self):
        class Server(MockServer):
            def handle_post_query(self, request):
                return httpx.Response(401)

        url = "https://example.com/shares/v2/share-id?apikey=k1"
        xport = httpx.MockTransport(Server(url))
        api = _api_client._ApiClient(url, transport=xport)
        with pytest.raises(errors.NetworkError):
            api.async_query()

    @pytest.mark.parametrize("code", [500, 502, 503, 504])
    def test_post_fails_on_50x(self, code):
        class Server(MockServer):
            def handle_post_query(self, request):
                return httpx.Response(code)

        url = "https://example.com/shares/v2/share-id?apikey=k1"
        xport = httpx.MockTransport(Server(url))
        api = _api_client._ApiClient(url, transport=xport)
        expected_error = errors.ServerError if code == 500 else errors.Retry
        with pytest.raises(expected_error):
            api.async_query()

    def test_post_no_location_header(self):
        class Server(MockServer):
            def handle_post_query(self, request):
                return httpx.Response(202)

        url = "https://example.com/shares/v2/share-id?apikey=k1"
        xport = httpx.MockTransport(Server(url))
        api = _api_client._ApiClient(url, transport=xport)
        with pytest.raises(errors.Error):
            api.async_query()

    def test_get_status_fails_on_network_error(self):
        class Server(MockServer):
            def handle_get_status(self, request):
                raise httpx.RequestError("failed")

        url = "https://example.com/shares/v2/share-id?apikey=k1"
        xport = httpx.MockTransport(Server(url))
        api = _api_client._ApiClient(
            url, transport=xport, sleep_before_first_status_query=0
        )
        with pytest.raises(errors.NetworkError):
            api.async_query()

    def test_get_status_302(self):
        url = "https://example.com/shares/v2/share-id?apikey=k1"
        events = ([{"uuid": str(uuid4())}],)
        xport = httpx.MockTransport(MockServer(url, events=events))
        api = _api_client._ApiClient(
            url, transport=xport, sleep_before_first_status_query=0
        )
        resp = api.async_query()
        assert resp.status_code == 200
        assert resp.json() == list(chain(*events))

    def test_get_status_202_302(self):
        class Server(MockServer):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.i = 0

            def handle_get_status(self, request):
                self.i += 1

                if self.i == 1:
                    return httpx.Response(202, headers={"Retry-After": "0"})
                else:
                    return super().handle_get_status(request)

        url = "https://example.com/shares/v2/share-id?apikey=k1"
        events = ([{"uuid": str(uuid4())}],)
        xport = httpx.MockTransport(Server(url, events=events))
        api = _api_client._ApiClient(
            url, transport=xport, sleep_before_first_status_query=0
        )
        resp = api.async_query()
        assert resp.status_code == 200
        assert resp.json() == list(chain(*events))

    @pytest.mark.parametrize("code", [502, 503, 504])
    def test_get_status_50x_302(self, code):
        class Server(MockServer):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.i = 0

            def handle_get_status(self, request):
                self.i += 1

                if self.i == 1:
                    return httpx.Response(code)
                else:
                    return super().handle_get_status(request)

        url = "https://example.com/shares/v2/share-id?apikey=k1"
        events = ([{"uuid": str(uuid4())}],)
        xport = httpx.MockTransport(Server(url, events=events))
        api = _api_client._ApiClient(
            url,
            transport=xport,
            sleep_before_first_status_query=0,
            sleep_after_50x_error_within_query=0,
        )
        resp = api.async_query()
        assert resp.status_code == 200
        assert resp.json() == list(chain(*events))

    @pytest.mark.parametrize("code", [400, 500])
    def test_get_status_40x_500(self, code):
        class Server(MockServer):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.i = 0

            def handle_get_status(self, request):
                self.i += 1

                if self.i == 1:
                    return httpx.Response(code)
                else:
                    return super().handle_get_status(request)

        url = "https://example.com/shares/v2/share-id?apikey=k1"
        xport = httpx.MockTransport(Server(url))
        api = _api_client._ApiClient(
            url, transport=xport, sleep_before_first_status_query=0
        )
        expected_error = errors.ServerError if code == 500 else errors.Retry
        with pytest.raises(expected_error):
            api.async_query()

    def test_get_status_no_locaton_header(self):
        class Server(MockServer):
            def handle_get_status(self, request):
                return httpx.Response(302)

        url = "https://example.com/shares/v2/share-id?apikey=k1"
        xport = httpx.MockTransport(Server(url))
        api = _api_client._ApiClient(
            url, transport=xport, sleep_before_first_status_query=0
        )
        with pytest.raises(errors.Error):
            api.async_query()

    def test_get_result_fails_on_network_error(self):
        class Server(MockServer):
            def handle_get_results(self, request):
                raise httpx.RequestError("failed")

        url = "https://example.com/shares/v2/share-id?apikey=k1"
        xport = httpx.MockTransport(Server(url))
        api = _api_client._ApiClient(
            url, transport=xport, sleep_before_first_status_query=0
        )
        with pytest.raises(errors.NetworkError):
            api.async_query()

    def test_get_result_410(self):
        class Server(MockServer):
            def handle_get_results(self, request):
                return httpx.Response(410)

        url = "https://example.com/shares/v2/share-id?apikey=k1"
        xport = httpx.MockTransport(Server(url))
        api = _api_client._ApiClient(
            url, transport=xport, sleep_before_first_status_query=0
        )
        with pytest.raises(errors.Retry):
            api.async_query()

    @pytest.mark.parametrize("code", [502, 503, 504])
    def test_get_result_50x_302(self, code):
        class Server(MockServer):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.i = 0

            def handle_get_results(self, request):
                self.i += 1

                if self.i == 1:
                    return httpx.Response(code)
                else:
                    return super().handle_get_results(request)

        url = "https://example.com/shares/v2/share-id?apikey=k1"
        events = ([{"uuid": str(uuid4())}],)
        xport = httpx.MockTransport(Server(url, events=events))
        api = _api_client._ApiClient(
            url,
            transport=xport,
            sleep_before_first_status_query=0,
            sleep_after_50x_error_within_query=0,
        )
        resp = api.async_query()
        assert resp.status_code == 200
        assert resp.json() == list(chain(*events))

    @pytest.mark.parametrize("code", [400, 500])
    def test_get_result_40x(self, code):
        class Server(MockServer):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.i = 0

            def handle_get_results(self, request):
                self.i += 1

                if self.i == 1:
                    return httpx.Response(code)
                else:
                    return super().handle_get_results(request)

        url = "https://example.com/shares/v2/share-id?apikey=k1"
        xport = httpx.MockTransport(Server(url))
        api = _api_client._ApiClient(
            url, transport=xport, sleep_before_first_status_query=0
        )
        expected_error = errors.ServerError if code == 500 else errors.Retry
        with pytest.raises(expected_error):
            api.async_query()
