"""Checkout flows: a plain verified chain, plus a monkey-patch trap."""

from shop.pricing import compute_tax, format_price


def total_with_tax(amount):
    return amount + compute_tax(amount)


def receipt(amount):
    return format_price(total_with_tax(amount))


def express_total(amount):
    """Statically this calls pricing.compute_tax. In the test suite
    it is only ever run with shop.checkout.compute_tax patched out,
    so the claimed edge is honestly UNVERIFIABLE, never VERIFIED."""
    return amount + compute_tax(amount)
