"""Switch: base, aggiornamenti e DLC dal nome; l'aggiornamento non e' un gioco a parte e parte con il base (Ryujinx)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import platforms as P, switchfiles as SF  # noqa: E402
from pozzo.library import launcher as L  # noqa: E402
from pozzo.scanner import list_entries  # noqa: E402

# nomi veri delle cartelle di un'installazione reale
CASES = {
    "Super Mario RPG [0100BC0018138000][v0].nsp": "base",
    "1-2-Switch [01000320000CC800][v65536].nsp": "update",
    "Boomerang Fu [010081A00EE62800] [v1245184].nsp": "update",
    "Boomerang Fu Just Desserts DLC [010081A00EE63002].nsp": "dlc",
    "Boomerang Fu [Fresh Flavors Pack DLC][010081A00EE63001].nsp": "dlc",
    "Mario Kart 8 Deluxe [0100152000022800][v1376256][US][Update v3.0.5].nsp": "update",
    "Little Nightmares III [010066101A55A000].xci": "base",
    "01007e100456c800.nsp": "update",  # solo l'ID, minuscolo
    "01007e100456c000.nsp": "base",
    "INAZUMA ELEVEN Victory Road [0100B36008F91002][v0][DLC 2].nsp": "dlc",
    "Gioco senza id [UPD].nsp": "update",
    "Gioco senza id.nsp": "base",
}


def test_tipo_dal_nome():
    for name, want in CASES.items():
        assert SF.kind(name) == want, name


def test_famiglia_e_versione():
    base = SF.family("Boomerang Fu [010081A00EE62000][v0].nsp")
    assert base == 0x010081A00EE62000
    for n in ("Boomerang Fu [010081A00EE62800] [v1245184].nsp", "x [010081A00EE63002].nsp", "x [010081A00EE63001].nsp"):
        assert SF.family(n) == base, n
    assert SF.version("Boomerang Fu [010081A00EE62800] [v1245184].nsp") == 1245184
    assert SF.version("Golf [01006FB00EBE0800] [983040].nsp") == 983040
    assert SF.version("Solo.nsp") == 0


def _files(tmp, *names):
    out = []
    for n in names:
        f = tmp / n
        f.write_bytes(b"x" * (10 if "800" in n or "DLC" in n else 100))
        out.append(f)
    return out


def test_pick_base_e_companions(tmp_path):
    base, up_old, up_new, dlc, other = _files(
        tmp_path, "Cuphead [0100A5C00D162000][v0].nsp", "Cuphead [0100A5C00D162800][v131072].nsp",
        "Cuphead [0100A5C00D162800][v655360].nsp", "Cuphead [0100A5C00D163001][v0] DLC.nsp", "Altro [0100AAAA0000A000][v0].nsp")
    allf = [base, up_old, up_new, dlc, other]
    assert SF.pick_base([up_old, up_new, base, other]) in (base, other)
    ups, dlcs = SF.companions(base, allf)
    assert ups == [up_new, up_old] and dlcs == [dlc]
    assert SF.pick_base([up_new, dlc]) is None


def test_la_scansione_non_mostra_l_aggiornamento_come_gioco(tmp_path):
    base, up, other = _files(tmp_path, "Super Mario RPG [0100BC0018138000][v0].nsp",
                             "Super Mario RPG [0100BC0018138800][v131072].nsp", "Altro [0100AAAA0000A000][v0].nsp")
    solo_up, = _files(tmp_path, "Orfano [0100BBBB0000B800][v65536].nsp")
    names = sorted(p.name for p, _ in list_entries(P.PLATFORMS["switch"], tmp_path))
    assert names == sorted([base.name, other.name, solo_up.name]), names  # l'aggiornamento senza base resta visibile


def test_ryujinx_riceve_l_aggiornamento_piu_nuovo(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    exe = tmp_path / "emu" / "Ryujinx.exe"
    exe.parent.mkdir()
    base, up1, up2 = _files(tmp_path, "G [0100AAAA0000A000][v0].nsp", "G [0100AAAA0000A800][v65536].nsp", "G [0100AAAA0000A800][v131072].nsp")
    got = L.register_switch_update(exe, base, [base, up1, up2])
    f = tmp_path / "appdata" / "Ryujinx" / "games" / "0100aaaa0000a000" / "updates.json"
    cfg = json.loads(f.read_text("utf-8"))
    assert got == up2 and cfg["selected"] == str(up2) and set(cfg["paths"]) == {str(up1), str(up2)}
    assert L.register_switch_update(exe, base, [base]) is None  # nessun aggiornamento: non tocca nulla
    (tmp_path / "emu" / "portable").mkdir()  # modalita' portable: i dati stanno accanto all'exe
    L.register_switch_update(exe, base, [base, up2])
    assert (tmp_path / "emu" / "portable" / "games" / "0100aaaa0000a000" / "updates.json").is_file()


def test_resolve_target_sceglie_il_base(tmp_path):
    d = tmp_path / "Gioco"
    d.mkdir()
    base, up = _files(d, "Gioco [0100AAAA0000A000][v0].nsp", "Gioco [0100AAAA0000A800][v65536].nsp")
    up.write_bytes(b"x" * 5000)  # anche se l'aggiornamento e' piu' grande
    assert L.resolve_target(P.PLATFORMS["switch"], d) == base


def test_nomi_storti_visti_nella_libreria_reale(tmp_path):
    # Title ID senza lo 0 iniziale (Pokemon Sword) e aggiornamento col Title ID del base (Rogue Prince)
    sword, upd = _files(tmp_path, "Pokemon Sword [0100ABF008968000][USA][v0].nsp", "Pokemon Sword [100ABF008968800] [v458752].nsp")
    assert SF.kind(upd.name) == "update" and SF.pick_base([sword, upd]) == sword
    rb, ru = _files(tmp_path, "Rogue [01008D9022462000].nsp", "Rogue [01008D9022462000][v131072][1.0.4].nsp")
    assert SF.pick_base([rb, ru]) == rb and SF.companions(rb, [rb, ru])[0] == [ru]
