"""Per-request context propagated via contextvars.

request_id_var holds the current request's X-Request-ID for the duration
of that request/response cycle, set by the request-ID middleware in
main.py. JSONFormatter (core/logging.py) reads it so every log line
emitted while handling a request carries the same request_id
automatically — call sites never pass it explicitly.
"""

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
