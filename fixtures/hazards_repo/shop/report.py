"""HAZARD: name shadowing (wrong-symbol trap).

This module defines its OWN format_price. render() calls the bare
name, which binds locally -- the traced run proves render ->
shop.report:format_price. A graph that resolves the name to
shop.pricing:format_price asserts an edge the evidence positively
contradicts: REFUTED / WRONG_SYMBOL."""


def format_price(amount):
    return f"USD {amount:.2f}"


def render(amount):
    return format_price(amount)
