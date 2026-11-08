"""Сборка RomFS-мода с русским переводом из архивов игрока.

    python -I tools/build.py <папка RomFS игры> <папка мода>

<папка RomFS игры> — файлы `.pak` с путями RomFS (tools/nsp_romfs.py extract). В мод пишутся
только изменённые архивы: `<папка мода>/romfs/<путь в RomFS>` — как мод Ryujinx/yuzu/Atmosphere,
который PrimeRecomp подхватывает из своей папки `mods` (R5).

Текст: блоки USEN и EUEN каждого MSBT получают русские строки из text/ru-labels.json (итог
tools/transfer.py, обновляется tools/sync_gc.py; язык зависит от языка системы — английский США
или Великобритании). Шрифты: FONT начертания 0 + атлас TXTR с
кириллицей (tools/font.py); шрифт меню берёт недостающие глифы у игрового. Архивы пересобираются
tools/pakwrite.py (без замен — байт в байт как у игры).
"""

import os
import json
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import font  # noqa: E402
import lzss  # noqa: E402
import msbt  # noqa: E402
import pak  # noqa: E402
import pakwrite  # noqa: E402

LANGS = ("USEN", "EUEN")
GAME_FONT = os.path.join("Preload", "MPR1", "GuiSysMP1.pak")
MENU_FONT = os.path.join("Preload", "MPRT", "PreloadFrontEndMPT.pak")
LABELS = os.path.join(HERE, "..", "text", "ru-labels.json")


def pack_asset(data):
    """Ресурс как в архиве: u32 режим LZSS и данные (режим 3 — группы по 4 байта, как у игры)."""
    mode = 3 if len(data) % 4 == 0 else 1
    return struct.pack("<I", mode) + lzss.compress(mode, data)


def text_assets(b, ru, used):
    """{guid: (новый MSBT, размер)} для MSBT архива, где что-то изменилось; used — найденные метки."""
    out = {}
    for t, g, v, off, us, cs in pak.resources(b):
        if t != "MSBT" or g in out:
            continue
        res = b[off:off + cs]
        blocks = msbt.lang_blocks(res)
        langs = {}
        for lang in LANGS:
            s, e = blocks[lang]
            m = res[s:e]
            rows = msbt.parse(m)
            used.update(label for label, _ in rows if label in ru)
            texts = [ru.get(label, text) for label, text in rows]
            if texts != [text for _, text in rows]:
                langs[lang] = msbt.build(m, texts)
        if langs:
            new = msbt.build_resource(res, langs)
            out[g] = (new, len(new))
    return out


def font_assets(path, donor=None):
    """(assets, metas) архива со шрифтом: FONT и атлас с кириллицей."""
    fb, atlas, meta = font.load_font(path)
    b = open(path, "rb").read()
    fguid = [r for r in pak.resources(b) if r[0] == "FONT"][0][1]
    tex = font.Font(fb).textures[0]
    nf, na, nm, added = font.cyrillize(fb, atlas, meta, None, donor)
    return {fguid: (pack_asset(nf), len(nf)), tex: (na, len(na))}, {tex: nm}, added


def build(romfs, mod):
    ru = json.load(open(LABELS, encoding="utf-8"))
    used = set()
    donor = font.donor_of(os.path.join(romfs, GAME_FONT))
    written = []
    for root, _, files in os.walk(romfs):
        for name in sorted(files):
            if not name.endswith(".pak"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, romfs)
            b = open(path, "rb").read()
            assets, metas = text_assets(b, ru, used), {}
            if rel in (GAME_FONT, MENU_FONT):
                fa, fm, added = font_assets(path, donor if rel == MENU_FONT else None)
                assets.update(fa)
                metas.update(fm)
            if not assets:
                continue
            written.append((rel, len(assets), len(b), pakwrite.rebuild(b, assets, metas)))
    missing = sorted(set(ru) - used)
    if missing:  # другая версия игры: строки не на своих местах — мод не пишется вовсе
        raise SystemExit(f"в архивах игры нет {len(missing)} строк перевода ({missing[:3]}): "
                         "нужна Metroid Prime Remastered v1.0.0 (010012101468C000)")
    for rel, n, a, nb in written:
        dst = os.path.join(mod, "romfs", rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, "wb").write(nb)
        print(f"  {rel}: {n} ресурсов, {a} -> {len(nb)} байт")
    print(f"мод: {len(written)} архивов, строк по-русски {len(ru)} -> {mod}")
    return written


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
