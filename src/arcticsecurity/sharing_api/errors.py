"""
Sharing API errors
"""

from typing import Any, Optional, Union

from ._util import parse_retry_after

__all__ = [
    "Error",
    "ConfigError",
    "InvalidTokenError",
    "ServerError",
    "NetworkError",
    "TimeoutError",
    "Retry",
]


class Error(Exception):
    """Base class for all errors."""

    def __init__(self, *args: Any, url: Optional[str] = None, **kwargs: Any):
        self.url = url
        super().__init__(*args, **kwargs)


class ConfigError(Error):
    """User error in query configuration.

    This error may be raised by this library or by the server.
    """

    pass


class InvalidTokenError(Error):
    """The server responded with "invalid token" error."""

    pass


class ServerError(Error):
    """The server responded with a error message.

    This results from a server which doesn't operate properly at the moment.
    """

    pass


class NetworkError(Error):
    """Error communicating with the sharing API server.

    This results from error communicating the with the sharing API server.
    """

    pass


class TimeoutError(Error):
    """Query to sharing API server timed out.

    The three-phase query to the sharing API exceeded the configured timeout.
    """

    pass


class Retry(NetworkError):
    """Network error that should be retried.

    This is raised from errors that are likely transient and may succeed if retried
    after some time.
    Attributes:
        after: Number of seconds the server asked the client to wait before
            retrying, or `None` if the server did not say (or said something
            unparseable). This value is advisory and is not bounded; the caller
            decides how long it is willing to wait.
    """

    def __init__(
        self, *args: Any, after: Union[str, int, float, None] = None, **kwargs: Any
    ):
        super().__init__(*args, **kwargs)

        self.after = parse_retry_after(after)
