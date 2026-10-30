"""Structured wall-time events shared by isolated CAD workers.

Events are opt-in so ordinary CLI builds retain their readable output. Stage
durations include nested stages; rendering has a separate measurement even
when it is part of an export stage.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import os
import time


PREFIX = 'VAULT_EVENT '
_enabled = ContextVar('vault_build_events', default=False)


@contextmanager
def event_output(enabled=True):
    token = _enabled.set(enabled)
    try:
        yield
    finally:
        _enabled.reset(token)


def emit(event, **details):
    if _enabled.get() or os.environ.get('VAULT_BUILD_EVENTS') == '1':
        print(PREFIX + json.dumps({'event': event,
              'timestamp': datetime.now(timezone.utc).isoformat(), **details},
              allow_nan=False), flush=True)


@contextmanager
def stage(name, **details):
    """Measure successful and failed phases without swallowing exceptions."""
    started = time.monotonic()
    emit('stage_started', stage=name, **details)
    error = None
    try:
        yield
    except BaseException as failure:
        error = f'{type(failure).__name__}: {failure}'
        raise
    finally:
        emit('stage_finished', stage=name, elapsed_seconds=time.monotonic() - started,
             failed=error is not None, error=error, **details)
