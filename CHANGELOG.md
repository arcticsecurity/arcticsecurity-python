# arcticsecurity-python

## Unreleased

### Changed

- Use `requests` (2.28.2 or newer) instead of `httpx` for HTTP.

## 0.2.0 - 2026-10-08

### Added

- `AuthError` for an invalid, expired or revoked API key.
- `allow_insecure` option to allow non-https share URLs.
- `max_unavailable_retries` to limit retries on 502/503/504 responses.
- `SyncReadResponse` and `Event` can be imported from `arcticsecurity.sharing_api`.
- Published API documentation.

### Changed

- Permanent 4xx errors raise `ConfigError` instead of `Retry`.
- `Query.query()` checks its arguments when it is called.
- Server responses in error messages and logs are truncated.

### Fixed

- API key no longer shown in the `repr` of internal objects, so it doesn't end
  up in logs, debuggers or error reports.
- `timeout` now also applies to sleeps between retries. Before, a long
  `Retry-After` could keep a query running past its timeout.
- `Retry-After` given as an HTTP date no longer raises `ValueError`, and long
  `Retry-After` values are capped.
- `projection` given as a generator or other one-shot iterable is sent
  correctly instead of as a broken query parameter.
- Malformed or non-list JSON responses raise `ServerError` instead of
  `JSONDecodeError` or returning the wrong results.
- Paging examples in the README and sync documentation now advance and save the
  token correctly. Before, some looped forever or lost the resume position.

## 0.1.0 - 2026-05-07

### Added

- Initial version.
