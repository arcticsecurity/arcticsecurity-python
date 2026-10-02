# Changelog

This project follows [Semantic Versioning v2](https://semver.org/spec/v2.0.0.html).
While the major version is `0`, a minor version bump may contain breaking changes.

## 0.2.0

### Breaking

- The share url must now use `https`. Pass
  `allow_insecure=True` to `Sync` or `Query` to opt out for a development server.
- Authentication and permanent client errors are classified as `AuthError` and
  `ConfigError` instead of `NetworkError` or `Retry`.
- `Query.query` validates its arguments eagerly, so a bad argument now raises
  when `query()` is called rather than when the returned generator is consumed.

### Added

- `AuthError`, raised when the server rejects the api key (401 / 403). It is a
  subclass of `ConfigError`, since it always means the share url needs fixing.
- `SyncReadResponse` and `Event` are exported from `arcticsecurity.sharing_api`.
- `user_agent` and `allow_insecure` are explicit keyword-only parameters of
  `Sync` and `Query`, so they show up in the signatures, the API documentation
  and type checkers. Unknown keyword arguments still raise `ValueError`, as
  before.

### Fixed

- The api key no longer appears in `repr()` or `str()` of the internal share url
  object, so it cannot leak into logs, tracebacks or error reporting tools.
- `Retry-After` is parsed safely: both a delay in seconds and an HTTP-date are
  accepted, unparseable values fall back to a default, and the resulting sleep is
  bounded so a broken or hostile server cannot block the caller indefinitely.
- The timeout budget is honoured during sleeps, and a delay that does not fit in
  the remaining budget ends the query instead of overshooting the timeout.
- Consecutive 502 / 503 / 504 responses within a query are bounded by
  `max_unavailable_retries`, so a query with `timeout=None` against an
  unavailable server no longer loops forever.
- A malformed or non-list response body raises `ServerError` instead of a raw
  `json.JSONDecodeError`, and a JSON object is no longer yielded as if its keys
  were events.
- Server response bodies echoed into error messages and log records are
  truncated. This includes the invalid-input errors returned on submit, so the
  `ConfigError` raised for them now carries a message string instead of the raw
  list of errors.
- A generator passed as `projection` is materialized during validation instead of
  being exhausted by it and then serialized by its `repr()`.

## 0.1.0

- Initial release: `Query` and `Sync` clients for the Arctic Security Sharing API.
