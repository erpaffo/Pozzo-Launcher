"""Multigiocatore locale: le portatili (cavo link) non contano, le console da salotto si'."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pozzo.app.server import _json, _players, _players_label
from starlette.responses import JSONResponse

# /api/library scritto a blocchi: byte identici a JSONResponse
_big = {"a": [[i, "è\"x", None, 1.5, True, [i]] for i in range(4500)], "b": {"c": [], "d": "ü"}, "e": list(range(2001))}
assert _json(_big) == JSONResponse(_big).body

assert _players("1-4", "gb") == 0
assert _players("2", "gba") == 0
assert _players("1-4", "ps2") == 4
assert _players("1-2", "switch") == 2
assert _players("16", "windows") == 0  # online
assert _players_label("1-2", "nds") == ""
assert _players_label("1-4", "snes") == "1–4 in locale"
print("ok")
