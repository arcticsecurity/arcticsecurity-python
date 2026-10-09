"""
Helpers for mocking HTTP with requests in tests.
"""

import json as jsonlib
from typing import Any, Callable, Optional

import requests
from requests.adapters import BaseAdapter
from requests.structures import CaseInsensitiveDict


def make_response(
    status_code: int,
    *,
    json: Any = None,
    text: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
    request: Optional[requests.PreparedRequest] = None,
) -> requests.Response:
    """Build a requests.Response, like httpx.Response(status, json=..., text=...)."""
    response = requests.Response()
    response.status_code = status_code
    response.headers = CaseInsensitiveDict(headers or {})
    response.encoding = "utf-8"

    if json is not None:
        response._content = jsonlib.dumps(json).encode("utf-8")
        response.headers.setdefault("Content-Type", "application/json")
    elif text is not None:
        response._content = text.encode("utf-8")
    else:
        response._content = b""

    if request is not None:
        response.request = request
        response.url = request.url or ""

    return response


class MockAdapter(BaseAdapter):
    """Transport adapter routing every request to a handler callable."""

    def __init__(
        self, handler: Callable[[requests.PreparedRequest], requests.Response]
    ):
        super().__init__()
        self.handler = handler

    def send(  # type: ignore[override]
        self, request: requests.PreparedRequest, **kwargs: Any
    ) -> requests.Response:
        response = self.handler(request)
        response.request = request
        response.url = request.url or ""
        return response

    def close(self) -> None:
        pass
