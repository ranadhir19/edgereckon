"""Tests for the hazards fixture.

These tests are the ground-truth instrument: edgereckon runs them
under sys.settrace and harvests the real caller->callee pairs. What
they deliberately do NOT exercise matters as much as what they do:

- notify() is only ever called with 'email' (send_sms never runs).
- route() is only ever called with 'home' (about_page never runs).
- express_total() is only ever run with compute_tax monkey-patched.
"""

import unittest

import shop.checkout as checkout_mod
from shop.checkout import receipt
from shop.container import build_checkout
from shop.dispatch import notify
from shop.events import emit
from shop.report import render
from shop.routes import route


def fake_compute_tax(amount):
    """Monkey-patch substitute. Lives in the test module on purpose:
    the traced substitute edge checkout.express_total ->
    tests.test_shop:fake_compute_tax is a real edge the static graph
    cannot claim."""
    return 0


class TestShop(unittest.TestCase):
    def test_receipt(self):
        self.assertEqual(receipt(100), "$120.00")

    def test_express_total_with_stubbed_tax(self):
        original = checkout_mod.compute_tax
        checkout_mod.compute_tax = fake_compute_tax
        try:
            self.assertEqual(checkout_mod.express_total(100), 100)
        finally:
            checkout_mod.compute_tax = original

    def test_notify_email_only(self):
        self.assertEqual(notify("email", "hi"), "email:hi")

    def test_container_checkout(self):
        svc = build_checkout()
        self.assertEqual(svc.checkout(200), 214.0)

    def test_route_home_only(self):
        self.assertEqual(route("home"), "home")

    def test_emit_ping(self):
        self.assertEqual(emit("ping", "x"), "pong:x")

    def test_render_uses_local_format_price(self):
        self.assertEqual(render(50), "USD 50.00")


if __name__ == "__main__":
    unittest.main()
