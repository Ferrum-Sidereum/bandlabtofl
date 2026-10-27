"""Compatibility fixes required before importing pyflp on Python 3.13+.

pyflp 2.2.1 constructs event IDs through ``EventEnum(value)``.  Python 3.14's
``EnumType.__call__`` refuses that call for an enum without members instead of
delegating to ``_missing_``, which pyflp relies on.  This shim restores the
pre-3.13 behaviour for pyflp's base enum only.
"""

from __future__ import annotations

from enum import EnumType

_PATCHED = False


def apply() -> None:
    global _PATCHED
    if _PATCHED:
        return

    original = EnumType.__call__

    def call(cls, value, *args, **kwargs):
        if (
            cls.__name__ == "EventEnum"
            and cls.__module__ == "pyflp._events"
            and not cls._member_map_
        ):
            member = cls._missing_(value)
            if member is None:
                raise ValueError(f"{value!r} is not a valid {cls.__name__}")
            return member
        return original(cls, value, *args, **kwargs)

    EnumType.__call__ = call
    _PATCHED = True
