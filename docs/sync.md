## Sync API

The `Sync` class reads all events matching user-provided conditions and provides tokens to enable reliable synchronization. Events are returned in database insertion order, which guarantees that no events are lost during synchronization.

### Methods

`Sync.read()` reads the next batch of events from the API. It returns a `SyncReadResponse` with the events (`events`), a continuation token (`token`), and a flag telling whether more events exist in the database at the moment (`has_more`).

A `token` should be provided for the `read()` call in all but the very first call. The `token` is returned by the `read()`. Using the `token` provides continuity in the events.

`Sync.seek()` sets the initial start time for synchronization. This is only used when no `token` is provided to `read()`. By default, synchronization starts from the current time.

See full documentation in the [API documentation](api.md#arcticsecurity.sharing_api.Sync.read)

### Paging Loop

Events can be synchronized from the Sync API with a simple paging loop. The `token` should be persisted between runs to resume synchronization.

```python
token = None  # Load the last known token from storage
while True:
    res = sync.read(token=token, pagesize=100)
    process(res.events)

    # Update the token before testing has_more. On the last batch the
    # server returns the last inserted token instead of a next token, and
    # that is what lets the next run resume where this one stopped.
    token = res.token

    if not res.has_more:
        break

# Save the token for the next run
```

### Initial Query

For the first query, a `token` will not exist. To configure the starting point of the synchronization, use either the `start` constructor argument or the `seek()` method. If no start time is configured, synchronization begins from the current time. To synchronize all events in the database, use a `start` time of `1` (a value of `0` means the current time).

```python
sync.seek(1)  # Start from the beginning of time
token = None
while True:
    res = sync.read(token=token, pagesize=100)
    process(res.events)

    # Always keep the token, also for an empty batch: it is the resume
    # point for the next run.
    token = res.token

    if not res.has_more:
        break
```

### Handling `InvalidTokenError`

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
token = None  # Load token from storage
last_inserted = None  # Load last insertion time from storage

while True:
    try:
        res = sync.read(token=token, pagesize=100)
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
        if res.events:
            # Process events and update the last known insertion time
            last_inserted = res.events[-1]["insertion time"]

        # Advance the token, then persist token and last_inserted together
        token = res.token

        if not res.has_more:
            # No more events
            break
```

