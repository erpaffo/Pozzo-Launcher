"""RetroArch extra (bezel, shader, cheat): merge dei file, parsing e abbinamento nomi, tutto offline."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import retroarch_extras as X  # noqa: E402


def test_merge_keeps_foreign_keys_and_backs_up_once(tmp_path):
    f = tmp_path / "Core" / "Game.cfg"
    f.parent.mkdir()
    f.write_text('video_smooth = "true"\n# nota\ninput_overlay = "vecchio.cfg"\n', encoding="utf-8")
    X.merge_cfg(f, {"input_overlay": "/x/retroarch_extras/b.cfg", "input_overlay_enable": "true"})
    X.merge_cfg(f, {"input_overlay_enable": "false"})
    txt = f.read_text(encoding="utf-8")
    assert 'video_smooth = "true"' in txt and "# nota" in txt
    assert 'input_overlay = "/x/retroarch_extras/b.cfg"' in txt and 'input_overlay_enable = "false"' in txt
    bak = f.with_name("Game.cfg.pozzo-bak")
    assert "vecchio.cfg" in bak.read_text(encoding="utf-8")  # copia dell'originale, non sovrascritta dal secondo merge
    X.merge_cfg(f, {"input_overlay": None, "input_overlay_enable": None})
    assert X.read_cfg(f) == {"video_smooth": "true"}


def test_cht_parse_and_toggle():
    text = 'cheats = 2\ncheat0_desc = "Vite infinite"\ncheat0_code = "7E0DBE-05"\ncheat0_enable = false\n' \
           'cheat1_desc = "Tempo"\ncheat1_code = "AAAA-BBBB"\ncheat1_enable = false\n'
    e = X.parse_cht(text)
    assert [(c["desc"], c["enable"]) for c in e] == [("Vite infinite", False), ("Tempo", False)]
    out = X.parse_cht(X.render_cht(e, {1}))
    assert [c["enable"] for c in out] == [False, True] and out[0]["code"] == "7E0DBE-05"


def test_cheat_name_matching():
    files = ["Super Mario World (USA).cht", "Super Mario Kart (USA).cht", "Zelda no Densetsu.cht"]
    assert X.match_cheat("Super Mario World (Europe) (Rev 1)", files) == "Super Mario World (USA).cht"
    assert X.match_cheat("Tetris", files) is None


def test_bezel_index_parsing():
    listing = [{"name": "Atari-2600-Bezel-16x9-2560x1440.cfg", "type": "file"},
               {"name": "Atari-2600-Bezel-16x9-2560x1440.png", "type": "file"},
               {"name": "Orfano.cfg", "type": "file"}, {"name": "sub", "type": "dir"}]
    assert X.parse_bezels(listing) == [{"id": "Atari-2600-Bezel-16x9-2560x1440.cfg", "name": "Atari-2600-Bezel-16x9-2560x1440"}]


def test_bezels_for_platform_and_set_bezel(tmp_path, monkeypatch):
    from pozzo import platforms as P
    monkeypatch.setattr(X, "cache_dir", lambda: tmp_path / "retroarch_extras")
    monkeypatch.setattr(X, "bezel_index", lambda: X.parse_bezels(
        [{"name": n + e, "type": "file"} for n in ("Nintendo-SNES-Bezel-16x9-2560x1440", "Sega-Saturn-Bezel-16x9-2560x1440") for e in (".cfg", ".png")]))
    monkeypatch.setattr(X, "fetch", lambda url: b"x")
    snes = X.bezels_for(P.PLATFORMS["snes"])
    assert [b["name"] for b in snes] == ["Nintendo-SNES-Bezel-16x9-2560x1440"]
    f = tmp_path / "g.cfg"
    X.set_bezel(f, snes[0]["id"])
    assert X.current_bezel(f) == snes[0]["id"]
    X.set_bezel(f, "")
    assert X.current_bezel(f) == ""
    try:
        X.bezel_file("../x.cfg")
        raise AssertionError
    except ValueError:
        pass


def test_shader_preset_file(tmp_path):
    root = tmp_path / "shaders" / "shaders_slang" / "crt"
    root.mkdir(parents=True)
    (root / "crt-geom.slangp").write_text("shaders = 1\n")
    assert [s["id"] for s in X.list_shaders(tmp_path)] == ["crt/crt-geom.slangp"]
    p = tmp_path / "config" / "Core" / "G.slangp"
    X.set_shader(p, tmp_path, "crt/crt-geom.slangp")
    assert X.current_shader(p, tmp_path) == "crt/crt-geom.slangp"
    X.set_shader(p, tmp_path, "")
    assert not p.exists()
    p.write_text("# mio\n")  # file dell'utente: non si tocca togliendo, si salva copia prima di sostituire
    X.set_shader(p, tmp_path, "")
    assert p.read_text() == "# mio\n"
    X.set_shader(p, tmp_path, "crt/crt-geom.slangp")
    assert p.with_name("G.slangp.pozzo-bak").read_text() == "# mio\n"
