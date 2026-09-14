"""Framework adapters. Thin by design: they extract the current user and
translate `(status, payload)` from `service.py` into an HTTP response. No
business rules live here — see service.py.
"""
