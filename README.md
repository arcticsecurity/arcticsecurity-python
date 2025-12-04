# Arctic Security library

Library to access Arctic Security Sharing API endpoints and retrieve event data.

## Features

- Query or Sync event data
- Pagination via opaque continuation tokens
- Filtering, projection (field selection), time range, reverse ordering (Query)
- Robust error handling (`ConfigError`, `NetworkError`, `Retry`, `TimeoutError`, `InvalidTokenError`, `ServerError`)
- Optional timeout and user-agent customization

## Installation

```bash
pip install arcticsecurity
```

Python >= 3.9 is required.

## Quick Start

### Query

```python
from arcticsecurity.sharing_api import Sync

url = "https://example.com/shares/v2/share-id?apikey=YOUR_API_KEY"
for event in Query(url).query(filter='"network owner"="Example Co"', max_events=50):
    print(event)
```

### Sync

```python
from datetime import datetime, timezone
from arcticsecurity.sharing_api import Query

url = "https://example.com/shares/v2/share-id?apikey=YOUR_API_KEY"
sync = Sync(url, filter='"network owner"="Example Co"', start=datetime(2025, 12, 1, tzinfo=timezone.utc))

# token can be fetched from a local storage
token = None

while True:
    token, events = sync.read(token=token)
    # process events
    if not events:
        break
```

## Query API

`Query` reads events matching user provided conditions. It can be used to fetch certain kind of events from the API as one-time queries.

Parameters:
- `filter`: rulelang filter expression
- `projection`: list of event field names to include
- `start`, `end`: timestamp boundaries (datetime, int, or float)
- `reverse`: newest first if `True`
- `max_events`: max number of events to return (0 means unlimited)
- `timeout`: max seconds to wait for each backend event retrieval (default 600)

Projection example:

```python
fields = ["uuid", "indicator", "severity"]
for e in Query(url).query(projection=fields):
    print(e)
```

Reverse ordering:

```python
for e in Query(url).query(reverse=True, max_events=10):
    print(e)
```

Custom user agent and timeout:

```python
for e in Query(url, user_agent="my-app/1.0").query(timeout=120):
    print(e)
```

Shortcut Function:

```python
from arcticsecurity.sharing_api import query

for e in query(url, filter="severity=high", max_events=10):
    print(e)
```

## Sync API

`Sync` reads all the events matching user-provided conditions, and provides tokens to enable synchronizing all the events from the API. The events are provided in database insertion order, which guarantees no events are lost.

```python
from arcticsecurity.sharing_api import Sync

url = "https://example.com/shares/v2/share-id?apikey=YOUR_API_KEY"
sync = Sync(url)
events, token = sync.read(pagesize=500, filter="category=malware")
print(f"Fetched {len(events)}; token: {token}")
```

Paging loop:

```python
token = None
while True:
    events, token = sync.read(token=token, pagesize=100)
    if not events:
        break
    process(events)
    if not token:
        break
```


## Error Handling & Retry

Exceptions:
- `ConfigError`: invalid URL or parameters
- `NetworkError`: transport/HTTP failure
- `Retry`: transient condition; optional `Retry.after` seconds hint
- `TimeoutError`: query timed out
- `InvalidTokenError`: invalid token in query
- `ServerError`: server-side error
- `Error`: base exception


### `InvalidTokenError`

`InvalidTokenError` may be raised in case the event the token points to does not exist in the server. There may be various reasons for this error:

- token has not been obtained from the server
- event has been deleted by e.g. database management
- event has expired via TTL

Synchronizing the events cannot be continued with the invalid token. Here's one way to tackle this problem.

- Synchonize events with `Sync.read()` normally
- Keep track of `insertion time` in the events
- If `InvalidTokenError`, `seek()` to the latest `insertion time` and continue from there

```python
while True:
    try:
        events, token = sync.read(token=token, pagesize=100)
    except InvalidTokenError:
        last_inserted = ... # fetch from the newest event
        token = None
        dt = datetime.strptime(last_inserted, "%Y-%m-%d %H:%M:%SZ").replace(tzinfo=timezone.utc)
        sync.seek(dt)
    else:
        # process events...
        
```


## Event Ordering

- `Query`: timestamp order (ascending unless `reverse=True`)
- `Sync`: insertion order (stable for checkpointing)

## User Agent & Versioning

The library sets a default user agent string including version and platform info. You can override it with the `user_agent` parameter to the class constructors.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

## Roadmap

- CHANGELOG and semantic versioning commitment

## Contributing

Issues and pull requests welcome. Add tests for new behavior.

## License

Add a `LICENSE` file (e.g. MIT or Apache-2.0) and reference it here.

## Status

Experimental (`0.1.x`); API may evolve. Pin versions for production use.
