# Arctic Security Library

A Python library to access Arctic Security's Sharing API endpoints and retrieve event data.

## Installation

```bash
pip install arcticsecurity
```

Python >= 3.9 is required.

## Quick Start

The library supports two distinct ways to retrieve events from the Sharing API: [`Query`](query.md) and [`Sync`](sync.md).

### Query

Use the [`Query`](query.md) class to perform one-off queries for specific events.

```python
from arcticsecurity.sharing_api import Query

url = "https://example.com/shares/v2/share-id?apikey=YOUR_API_KEY"
for event in Query(url).query(filter='"network owner"="Example Co"', max_events=50):
    print(event)
```

### Sync

Use the [`Sync`](sync.md) class to reliably synchronize all event data. It uses pagination with opaque continuation tokens to ensure no events are missed.

Here `Sync` means keeping your own copy of the events synchronized. It is unrelated to the Sharing API's synchronous endpoints: both classes use the asynchronous ones.

```python
from arcticsecurity.sharing_api import Sync

url = "https://example.com/shares/v2/share-id?apikey=YOUR_API_KEY"
sync = Sync(url, filter='"network owner"="Example Co"')

# Load the token stored by the previous run, or None on the first run
token = None

while True:
    res = sync.read(token=token, pagesize=1000)
    # process res.events...

    # res.token is None when the server reported no position; keep the old one
    if res.token is not None:
        token = res.token

    if not res.has_more:
        break

# store the token for the next run
```

## Sharing API URL

Both `Query()` and `Sync()` require a share API URL. The URL must include an `apikey` query parameter. The API key is parsed from the URL and sent in the `Authorization` header.

If the server rejects the API key, an `AuthError` is raised.

Example URL:
`https://example.com/shares/v2/share-id?apikey=YOUR_API_KEY`

The URL may also contain other valid query parameters. These are parsed and included in the backend requests. Parameters provided in `Query.query()` or `Sync.read()` override any defaults set in the URL.

## User Agent & Versioning

The library sets a default user-agent string that includes its version and platform information. You can override this by passing the `user_agent` parameter to the class constructors.

## Development

[uv](https://docs.astral.sh/uv/) is required.

```bash
uv sync --group dev

uv run ruff format .
uv run ruff check --fix .
uv run pytest
uv run mypy --config-file pyproject.toml -p arcticsecurity
```
