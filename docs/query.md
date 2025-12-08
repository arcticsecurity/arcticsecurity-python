## Query API

The `Query` class reads events that match user-provided conditions. It is ideal for fetching specific events from the API in one-time queries.

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


