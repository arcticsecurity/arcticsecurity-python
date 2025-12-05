# Arctic Security Library

A Python library to access Arctic Security's Sharing API endpoints and retrieve event data.

## Installation

```bash
pip install arcticsecurity
```

Python >= 3.9 is required.

## Quick Start

### Query

Use the `Query` class to perform one-off queries for specific events.

```python
from arcticsecurity.sharing_api import Query

url = "https://example.com/shares/v2/share-id?apikey=YOUR_API_KEY"
for event in Query(url).query(filter='"network owner"="Example Co"', max_events=50):
    print(event)
```

### Sync

Use the `Sync` class to reliably fetch all event data. It uses pagination with opaque continuation tokens to ensure no events are missed.

```python
from arcticsecurity.sharing_api import Sync

url = "https://example.com/shares/v2/share-id?apikey=YOUR_API_KEY"
sync = Sync(url, filter='"network owner"="Example Co"')

# Fetch token from previous run
token = ...

while True:
    events, token = sync.read(token=token, pagesize=1000)
    if not events:
        break
    # process events...

# store the token for the next run
```

## Common features

- Robust error handling with specific exceptions (`ConfigError`, `NetworkError`, `Retry`, `TimeoutError`, `InvalidTokenError`, `ServerError`).
- Optional timeout and user-agent customization

## Query API

The `Query` class reads events that match user-provided conditions. It is ideal for fetching specific events from the API in one-time queries.

### Parameters

`Query.query()` (and its shortcut `query()`) returns a generator that reads the events matching the query from the backend.

It accepts the following parameters:

- `filter`: A rulelang filter expression.
- `projection`: A list of event field names to include in the results.
- `start`, `end`: Timestamp boundaries for the query (can be `datetime`, `int`, or `float`). Defaults to the entire available time range.
- `reverse`: If `True`, returns the newest events first.
- `max_events`: The maximum number of events to return (0 means unlimited).
- `timeout`: The maximum number of seconds to wait for each backend event retrieval (default: 600).
- `pagesize`: The maximum number of events per page requested from the backend (default: 1000).
- `user_agent`: An optional custom user-agent string.

### Timeout

The `timeout` parameter applies to a single retrieval of a batch of events from the backend. There is no overall timeout for the generator returned by `query()`.


### Examples

**Projection:**

```python
fields = ["uuid", "indicator", "severity"]
for e in Query(url).query(projection=fields):
    print(e)
```

**Reverse ordering:**

```python
for e in Query(url).query(reverse=True, max_events=10):
    print(e)
```

**Custom user agent and timeout:**

```python
for e in Query(url, user_agent="my-app/1.0").query(timeout=120):
    print(e)
```

**Shortcut Function `query()`:**

```python
from arcticsecurity.sharing_api import query

for e in query(url, filter="severity=high", max_events=10):
    print(e)
```

## Sync API

The `Sync` class reads all events matching user-provided conditions and provides tokens to enable reliable synchronization. Events are returned in database insertion order, which guarantees that no events are lost during synchronization.

### Methods

`Sync.read()` reads the next batch of events from the API. It returns a list of events and a continuation token.

It accepts the following parameters:

- `token`: The continuation token from the previous `read()` call.
- `pagesize`: The maximum number of events to retrieve in one batch (default: 1000).
- `timeout`: The maximum number of seconds to wait for the backend response (default: 600).

`Sync.seek()` sets the initial start time for synchronization. This is only used when no `token` is provided to `read()`. By default, synchronization starts from the current time.

### Paging Loop

Events can be synchronized from the Sync API with a simple paging loop. The `token` should be persisted between runs to resume synchronization.

```python
token = None # Load the last known token from storage
while True:
    events, token = sync.read(token=token, pagesize=100)
    if not events:
        break
    process(events)
# Save the token for the next run
```

### Initial Query

For the first query, a `token` will not exist. To configure the starting point of the synchronization, use either the `start` constructor argument or the `seek()` method. If no start time is configured, synchronization begins from the current time. To synchronize all events in the database, use a `start` time of `1` (a value of `0` means the current time).

```python
sync.seek(1) # Start from the beginning of time
token = None
while True:
    events, token = sync.read(token=token, pagesize=100)
    if not events:
        break
    process(events)
```

## Sharing API URL

Both `Query()` and `Sync()` require a share API URL. The URL must include an `apikey` query parameter. The API key is parsed from the URL and sent in the `Authorization` header.

Example URL:
`https://example.com/shares/v2/share-id?apikey=YOUR_API_KEY`

The URL may also contain other valid query parameters. These are parsed and included in the backend requests. Parameters provided in `Query.query()` or `Sync.read()` override any defaults set in the URL.

## Error Handling & Retry

The library raises the following exceptions:

- `ConfigError`: Invalid URL or parameters.
- `NetworkError`: Transport or HTTP failure.
- `Retry`: A transient condition occurred; the request can be retried. The exception may include a `after` attribute with a suggested delay in seconds.
- `TimeoutError`: The query timed out.
- `InvalidTokenError`: The continuation token is invalid.
- `ServerError`: A server-side error occurred.
- `Error`: The base exception for all library-specific errors.


### `InvalidTokenError`

`InvalidTokenError` may be raised if the event the token points to no longer exists on the server. This can happen if:

- The token is malformed or has not been obtained from the server.
- The event has been deleted by database management.
- The event has expired due to a TTL policy.

Synchronization cannot be continued with an invalid token. One way to handle this is to restart the synchronization from the timestamp of the last successfully processed event.

```python
import dateutil.parser
from arcticsecurity.sharing_api import Sync
from arcticsecurity.sharing_api.errors import InvalidTokenError

sync = Sync(url)
token = None # Load token from storage
last_inserted = None # Load last insertion time from storage

while True:
    try:
        events, token = sync.read(token=token, pagesize=100)
    except InvalidTokenError:
        if last_inserted:
            # Reset the token and seek to the last known insertion time
            token = None
            dt = dateutil.parser.parse(last_inserted)
            sync.seek(dt)
        else:
            # Cannot recover, handle the error (e.g., log and exit)
            raise
    else:
        if events:
            # Process events and update the last known insertion time
            last_inserted = events[-1]["insertion time"]
            # Persist token and last_inserted
        else:
            # No more events
            break
```

## User Agent & Versioning

The library sets a default user-agent string that includes its version and platform information. You can override this by passing the `user_agent` parameter to the class constructors.

## Development

```bash
pip install -e ".[dev]"

ruff check .
pytest
```

## Roadmap

- Add a `CHANGELOG` and commit to semantic versioning.

## Contributing

Issues and pull requests are welcome. Please add tests for any new behavior.

## License

Add a `LICENSE` file (e.g., MIT or Apache-2.0) and reference it here.

## Status

Experimental (`0.1.x`); the API may evolve. Pin the library version for production use.
