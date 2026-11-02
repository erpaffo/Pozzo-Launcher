import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pozzo.cli import want_bigpicture


def test_want_bigpicture():
    off, on = NS(app={}), NS(app={"start_bigpicture": True})
    assert not want_bigpicture(off)
    assert want_bigpicture(on)
    assert want_bigpicture(off, flag=True)
    assert not want_bigpicture(on, no_flag=True)
    assert not want_bigpicture(on, flag=True, no_flag=True)


if __name__ == "__main__":
    test_want_bigpicture()
    print("ok  avvio in Big Picture: flag, impostazione, entrambi")
