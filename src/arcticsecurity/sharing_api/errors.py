"""
Sharing API errors
"""

from typing import Any, Union


class Error(Exception):
    pass


class ConfigError(Error):
    """User error in query configuration."""

    pass


class InvalidTokenError(Error):
    """Invalid token in query."""

    pass


class ServerError(Error):
    """Error in the sharing API server."""

    pass


class NetworkError(Error):
    """Error communicating with the sharing API."""

    pass


class TimeoutError(Error):
    """Query timed out."""

    pass


class Retry(NetworkError):
    """Network error that should be retried."""

    def __init__(self, *args: Any, after: Union[str, int, None] = None, **kwargs: Any):
        super().__init__(*args, **kwargs)

        if after is None:
            self.after = None
        else:
            try:
                self.after = int(after)
            except ValueError:
                self.after = None
