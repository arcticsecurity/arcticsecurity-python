"""
Sharing API errors
"""

from typing import Any, Union

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

    pass


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
    """

    def __init__(self, *args: Any, after: Union[str, int, None] = None, **kwargs: Any):
        super().__init__(*args, **kwargs)

        if after is None:
            self.after = None
        else:
            try:
                self.after = int(after)
            except ValueError:
                self.after = None
