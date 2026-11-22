"""HAZARD: decorator registry.

Handlers register themselves by decorator at import time; emit()
dispatches through the registry dict. The emit -> handle_ping edge
exists only at runtime. The traced run proves it; a static graph
cannot claim it."""

_HANDLERS = {}


def on_event(name):
    def deco(fn):
        _HANDLERS[name] = fn
        return fn
    return deco


@on_event("ping")
def handle_ping(payload):
    return "pong:" + payload


def emit(name, payload):
    return _HANDLERS[name](payload)
