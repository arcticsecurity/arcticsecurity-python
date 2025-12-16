# Arctic Security Library

A Python library to access Arctic Security's Sharing API endpoints and retrieve event data.

## Installation

```bash
pip install arcticsecurity
```

Python >= 3.9 is required.

## Quick Start

The library supports two distinct ways to retrieve events from the Sharing API: `Query` and `Sync`.

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

## Development

[uv](https://docs.astral.sh/uv/) is required.

```bash
uv sync --group dev

uv ruff check .
uv pytest
```

## Roadmap

- Add a `CHANGELOG` and commit to semantic versioning.

## Contributing

Issues and pull requests are welcome. Please add tests for any new behavior.

## License

Add a `LICENSE` file (e.g., MIT or Apache-2.0) and reference it here.

## Status

Experimental (`0.1.x`); the API may evolve. Pin the library version for production use.
