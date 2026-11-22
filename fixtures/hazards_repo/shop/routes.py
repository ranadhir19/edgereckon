"""HAZARD: string-based routing.

ROUTES maps names to function *names*; route() resolves the target
through globals() at runtime. No static call edge out of route()
exists to claim. The tests exercise only 'home'."""


def home_page():
    return "home"


def about_page():
    return "about"


ROUTES = {"home": "home_page", "about": "about_page"}


def route(name):
    fn = globals()[ROUTES[name]]
    return fn()
