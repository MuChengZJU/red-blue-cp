"""Deprecated location — moved to ``app.extract.pricing`` in 0.6.

Kept as a backward-compat shim for 0.5.x imports; removed in 0.7.
Forwards every public and private name to the new module so existing
``from app.service.pricing import ...`` keeps resolving to the same objects.
"""
from app.extract.pricing import *  # noqa: F401,F403
from app.extract import pricing as _src


def __getattr__(name):  # PEP 562: forward privates (e.g. _helpers) the star-import skips
    return getattr(_src, name)
