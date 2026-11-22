"""HAZARD: dependency-injection container.

CheckoutService never names TaxService; the container wires them at
runtime. A static graph can see build_checkout() instantiating the
classes, but the checkout -> TaxService.tax edge is invisible to it.
The traced run proves the edge is real (a recall miss for the static
graph, a VERIFIED edge for any graph that claims it)."""


class Container:
    def __init__(self):
        self._registry = {}

    def register(self, name, obj):
        self._registry[name] = obj

    def resolve(self, name):
        return self._registry[name]


class TaxService:
    def tax(self, amount):
        return round(amount * 0.07, 2)


class CheckoutService:
    def __init__(self, container):
        self.container = container

    def checkout(self, amount):
        svc = self.container.resolve("tax")
        return amount + svc.tax(amount)


def build_checkout():
    container = Container()
    container.register("tax", TaxService())
    return CheckoutService(container)
