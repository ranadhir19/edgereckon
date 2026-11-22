"""HAZARD: registry / dict dispatch.

The call target is a value pulled out of a dict at runtime. A static
graph sees no call edge out of notify() at all; a naive graph may
assert edges to every registry value. Only the 'email' path is
exercised by the tests, so notify -> send_email is VERIFIED and
notify -> send_sms is UNVERIFIABLE when a graph claims it."""


def send_email(msg):
    return "email:" + msg


def send_sms(msg):
    return "sms:" + msg


HANDLERS = {"email": send_email, "sms": send_sms}


def notify(kind, msg):
    handler = HANDLERS[kind]
    return handler(msg)
