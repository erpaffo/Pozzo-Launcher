"""Adattatori per emulatore: un modulo per ciascuno, caricato solo quando serve."""

from __future__ import annotations

import importlib

ADAPTER_MODULES = ("retroarch", "dolphin", "pcsx2", "duckstation", "rpcs3", "cemu", "ryujinx")


def get(name: str):
    """Modulo dell'adattatore o None se l'emulatore non è supportato."""
    if name not in ADAPTER_MODULES:
        return None
    try:
        return importlib.import_module(f"{__name__}.{name}")
    except ModuleNotFoundError as exc:
        if exc.name == f"{__name__}.{name}":
            return None
        raise
