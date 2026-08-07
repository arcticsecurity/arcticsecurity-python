"""
Internal helpers.
"""

import email.utils
import time
from typing import Any, Optional

# Upper bound for a delay the server asks us to wait. Without this a broken or
# hostile server could block the calling thread for an arbitrarily long time.
MAX_RETRY_AFTER = 60.0


def parse_retry_after(value: Any) -> Optional[float]:
    """Parse a `Retry-After` header value into a number of seconds.

    Per RFC 9110 the value is either a number of seconds or an HTTP-date. Both
    are accepted here. Returns `None` if the value cannot be parsed.

    >>> parse_retry_after("5")
    5.0
    >>> parse_retry_after(2)
    2.0
    >>> parse_retry_after("1.5")
    1.5
    >>> parse_retry_after("-10")
    0.0
    >>> parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT")
    0.0
    >>> parse_retry_after("not a date") is None
    True
    >>> parse_retry_after(None) is None
    True
    """
    if value is None:
        return None

    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        pass

    try:
        # parsedate_to_datetime raises TypeError on py3.9 and ValueError on
        # py3.10+ for unparseable input
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, AttributeError):
        return None

    if dt is None:
        return None

    return max(0.0, dt.timestamp() - time.time())


def retry_after_delay(
    value: Any, default: float, maximum: float = MAX_RETRY_AFTER
) -> float:
    """Sleep duration to honour a `Retry-After` header, bounded by `maximum`.

    >>> retry_after_delay("5", 1)
    5.0
    >>> retry_after_delay("999999", 1)
    60.0
    >>> retry_after_delay("garbage", 1)
    1.0
    >>> retry_after_delay(None, 1)
    1.0
    """
    delay = parse_retry_after(value)
    if delay is None:
        delay = float(default)

    return min(delay, maximum)
