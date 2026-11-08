"""Русский перевод Metroid Prime Remastered для PrimeRecomp: мод из своей копии игры одной командой.

    python install.py <игра.nsp> [--keys <prod.keys>] [--mods <папка mods PrimeRecomp>]

Ключи: по умолчанию prod.keys рядом с NSP, затем ~/.switch/prod.keys (где их держат Ryujinx и yuzu).
Папка модов: Linux — ~/.local/share/primerecomp/mods, macOS —
~/Library/Application Support/io.github.primerecomp/mods; на Windows она рядом с PrimeRecomp.exe,
её нужно указать (--mods). Мод пишется в <mods>/russian; прежняя версия мода заменяется.
"""

import argparse
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools"))
import build  # noqa: E402
import nsp_romfs  # noqa: E402

# архивы со строками и шрифтами (v1.0.0); остальная игра не нужна
PAKS = ("MiscData.pak", "KernelMPRT.pak", "StartupUI.pak", "Preload/MPR1/GameplayOverrides.pak",
        "Preload/MPR1/GuiSysMP1.pak", "Preload/MPR1/PreloadMP1.pak", "Preload/MPRT/PreloadFrontEndMPT.pak",
        "UI/MPR1/UIMP1.pak")
MOD = "russian"


def default_mods():
    if sys.platform == "win32":
        return None
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "io.github.primerecomp", "mods")
    xdg = os.environ.get("XDG_DATA_HOME", "")
    base = xdg if xdg.startswith("/") else os.path.join(home, ".local", "share")
    return os.path.join(base, "primerecomp", "mods")


def find_keys(nsp):
    for p in (os.path.join(os.path.dirname(os.path.abspath(nsp)), "prod.keys"),
              os.path.join(os.path.expanduser("~"), ".switch", "prod.keys")):
        if os.path.isfile(p):
            return p
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Русский мод Metroid Prime Remastered для PrimeRecomp")
    ap.add_argument("nsp", help="свой дамп игры: файл .nsp (v1.0.0, 010012101468C000)")
    ap.add_argument("--keys", help="prod.keys своей консоли (по умолчанию — рядом с NSP)")
    ap.add_argument("--mods", help="папка mods PrimeRecomp")
    a = ap.parse_args(argv)
    keys = a.keys or find_keys(a.nsp)
    if not keys or not os.path.isfile(keys):
        raise SystemExit("не найден prod.keys: положите его рядом с NSP или укажите --keys")
    mods = a.mods or default_mods()
    if not mods:
        raise SystemExit("укажите папку mods рядом с PrimeRecomp.exe: --mods <папка>\\mods")

    print(f"игра: {a.nsp}\nключи: {keys}")
    rom = nsp_romfs.open_romfs(a.nsp, keys)
    entries = {path.lstrip("/"): (off, size) for path, off, size in rom.walk()}
    lost = [p for p in PAKS if p not in entries]
    if lost:
        raise SystemExit(f"в игре нет {lost}: нужна Metroid Prime Remastered v1.0.0 (010012101468C000)")
    with tempfile.TemporaryDirectory(prefix="mpr-ru-") as tmp:
        romfs, out = os.path.join(tmp, "romfs"), os.path.join(tmp, MOD)
        for p in PAKS:
            dst = os.path.join(romfs, p)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, "wb").write(rom.read_file(*entries[p]))
        print(f"извлечено архивов: {len(PAKS)}; сборка (несколько минут)…")
        build.build(romfs, out)
        dst = os.path.join(mods, MOD)
        shutil.rmtree(dst, ignore_errors=True)
        os.makedirs(mods, exist_ok=True)
        shutil.move(out, dst)
    print(f"готово: {dst}\nPrimeRecomp: F1 → Mods — мод «{MOD}» включён сам, если его не выключали.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
