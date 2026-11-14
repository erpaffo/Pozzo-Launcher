"""Lettore XInput condiviso: gli slot vuoti si rileggono solo ogni 1,5 s, quelli collegati ogni giro."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pozzo.library import launcher as L  # noqa: E402

def test_xinput_reader():
    calls = []
    state = {1: 0x0030}  # solo lo slot 1 collegato


    def get(i):
        calls.append(i)
        return state.get(i)


    t = [100.0]
    read = L._xinput_reader(get, clock=lambda: t[0])
    assert read() == 0x0030 and sorted(calls) == [0, 1, 2, 3], calls  # primo giro: li prova tutti
    calls.clear()
    t[0] += 0.05
    assert read() == 0x0030 and calls == [1], calls  # slot vuoti saltati, quello collegato letto
    calls.clear()
    state[2] = 0x0200  # collegato a meta': visto entro 1,5 s
    t[0] += 1.5
    assert read() == 0x0230 and sorted(calls) == [0, 1, 2, 3], calls
    calls.clear()
    state.clear()  # scollegati tutti: dopo un giro si fermano
    t[0] += 0.05
    read(); calls.clear()
    t[0] += 0.05
    assert read() == 0 and calls == [], calls


if __name__ == "__main__":
    test_xinput_reader()
    print("ok  lettore XInput condiviso")
