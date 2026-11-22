"""Plain, statically visible pricing helpers."""


def compute_tax(amount):
    """The real tax function. One test monkey-patches the copy bound
    in shop.checkout, so the claimed edge checkout.express_total ->
    compute_tax is never observed at runtime."""
    return round(amount * 0.2, 2)


def format_price(amount):
    """The 'utility' format_price. shop.report defines its own local
    format_price of the same name -- a wrong-symbol trap for graphs
    that resolve the bare name to this module."""
    return f"${amount:.2f}"
