"""Link pozzo:// passato alla CLI: decisione in cli._join_action (senza avviare l'app)."""
import pytest  # noqa: F401 - segnala a packaging/run_tests.py di eseguire il file con pytest

from pozzo import cli

LINK = "pozzo://join/ABC123"


def test_no_link_unchanged():
    called = []
    assert cli._join_action([], forward=lambda *a, **k: called.append(a) or True) is None
    assert cli._join_action(["app", "--port", "9000"], forward=lambda *a, **k: True) is None
    assert called == []


def test_valid_link_forwarded_means_focus():
    seen = []

    def fake_forward(url, port=8765):
        seen.append((url, port))
        return True

    assert cli._join_action([LINK], forward=fake_forward) == ("focus", None)
    assert seen == [(LINK, 8765)]


def test_valid_link_not_forwarded_means_pending():
    assert cli._join_action([LINK], forward=lambda *a, **k: False) == ("pending", "ABC123")


def test_scheme_case_insensitive():
    assert cli._join_action(["POZZO://join/XYZ"], forward=lambda *a, **k: False) == ("pending", "XYZ")


def test_invalid_link_ignored():
    assert cli._join_action(["pozzo://altro/ABC"], forward=lambda *a, **k: False) == ("ignore", None)
    assert cli._join_action(["pozzo://join/"], forward=lambda *a, **k: False) == ("ignore", None)
