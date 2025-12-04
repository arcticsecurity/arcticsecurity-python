# Arctic Security library

Library to access Arctic Security Sharing API endpoints and retrieve event data.

## Features

- Query (stream) or Sync (page) event data
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

```python
from arcticsecurity.sharing_api import Query

url = "https://example.com/shares/v2/share-id?apikey=YOUR_API_KEY"
for event in Query(url).query(filter="severity>=3", max_events=50):
    print(event)
```

## Query API

`Query` streams events, following `x-next-token` until exhausted.

Parameters:
- `filter`: server-side filter expression
- `projection`: str or sequence of field names to include
- `start`, `end`: timestamp boundaries (datetime, int, float, or string)
- `reverse`: newest first if True
- `limit`: max events per page (server may cap)
- `max_events`: client-side cap (0 or None means unlimited)
- `token`: resume from previous token
- `timeout`: max seconds to wait for each query (default 600)
- `user_agent`: custom user agent string (optional)

Projection example:

```python
fields = ["uuid", "indicator", "severity"]
for e in Query(url).query(projection=fields):
    print(e)
```

Resume from token:

```python
token = "opaque-token"
for e in Query(url).query(token=token):
    ...
```

Reverse ordering:

```python
for e in Query(url).query(reverse=True, max_events=10):
    ...
```

Custom user agent and timeout:

```python
for e in Query(url, user_agent="my-app/1.0").query(timeout=120):
    ...
```

## Sync API

`Sync` fetches one page sorted by insertion time and returns `(events, continuation_token)`.

```python
from arcticsecurity.sharing_api import Sync

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

Custom user agent and timeout:

```python
sync = Sync(url, user_agent="my-app/1.0")
events, token = sync.read(timeout=120)
```

## Shortcut Function

```python
from arcticsecurity.sharing_api import query

for e in query(url, filter="severity>=3", max_events=10):
    ...
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

Basic retry loop:

```python
from arcticsecurity.sharing_api import Query, errors
import time

q = Query(url)
while True:
    try:
        for e in q.query(max_events=100):
            handle(e)
        break
    except errors.Retry as r:
        time.sleep(r.after or 5)
    except errors.TimeoutError:
        print("Timed out, retrying...")
        time.sleep(5)
    except errors.NetworkError:
        break
```

Recommended: exponential backoff for repeated `Retry`.

## Event Ordering

- `Query`: timestamp order (ascending unless `reverse=True`)
- `Sync`: insertion order (stable for checkpointing)

## Best Practices

- Persist last token for incremental syncs.
- Use `max_events` to bound memory in streaming.
- Treat `Retry` as transient; backoff appropriately.

## API Surface

- Classes: `Query`, `Sync`
- Function: `query(url, **kwargs)`
- Exceptions: `ConfigError`, `NetworkError`, `Retry`, `TimeoutError`, `InvalidTokenError`, `ServerError`, `Error`

## User Agent & Versioning

The library sets a default user agent string including version and platform info. You can override it with the `user_agent` parameter.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

## Roadmap

- Optional timeout configuration
- Typed event model (TypedDict / Pydantic optional)
- User-Agent customization
- Additional `Sync` tests & reverse query tests
- CHANGELOG and semantic versioning commitment

## Contributing

Issues and pull requests welcome. Add tests for new behavior.

## License

Add a `LICENSE` file (e.g. MIT or Apache-2.0) and reference it here.

## Status

Experimental (`0.1.x`); API may evolve. Pin versions for production use.
