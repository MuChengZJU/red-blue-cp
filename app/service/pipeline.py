"""Deprecated location — moved to ``app.extract.pipeline`` in 0.6.

Kept as a backward-compat shim for 0.5.x imports; removed in 0.7.
Forwards every public and private name to the new module so existing
``from app.service.pipeline import ...`` keeps resolving to the same objects.
"""
from app.extract.pipeline import *  # noqa: F401,F403
from app.extract import pipeline as _src


def __getattr__(name):  # PEP 562: forward privates (e.g. _helpers) the star-import skips
    return getattr(_src, name)
