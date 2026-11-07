"""Самопроверки форматов и правил переноса. Без данных игры — синтетика; с work/romfs — ещё и
настоящие ресурсы.

    python -I tools/test_formats.py
"""

import glob
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import collections  # noqa: E402

import lzss  # noqa: E402
import rtext  # noqa: E402
import transfer  # noqa: E402
import txtr  # noqa: E402

ROMFS = os.path.join(HERE, "..", "work", "romfs")
# не меньше стольких строк по-русски (храповик: число только растёт); ручных — ноль
MIN_AUTO = 2893


def synthetic():
    rnd = random.Random(1)
    for mode in (1, 2, 3):
        g = 1 << (mode - 1)
        data = bytes(rnd.choice(b"ab\0\xff") for _ in range(4096 * g)) + bytes(1000 * g)
        assert lzss.decompress(mode, lzss.compress(mode, data), len(data)) == data, mode
    px = bytes(rnd.randrange(256) for _ in range(416 * 512))
    assert txtr.deswizzle(txtr.swizzle(px, 416, 512), 416, 512) == px
    words = collections.Counter({"мерцающая": 3, "пират-невидимка": 2, "пират": 5})
    assert transfer.unbreak("Мерцаю-\nщая мышь", words) == "Мерцающая мышь"
    assert transfer.unbreak("Пират-\nневидимка", words) == "Пират-невидимка"
    assert transfer.unbreak("Робот-под-\nжигатель", words) is None
    red, reset = "\x0e\x00\x03\x04ab", "\x0e\x00\x03\x04\x00＀"
    en_rm = f"{red}Cordite{reset} casing is weak."
    rep = []
    out = transfer.russian("[00000001]_000", en_rm,
                           {"00000001": {"0": {"ru": "Оболочка из &main-color=#FF3333;кордита&main-color=#89D6FF; слаба."}}},
                           {"00000001": {"strings": ["&main-color=#FF3333;Cordite&main-color=#89D6FF; casing is weak."]}},
                           words, {}, rep, {})
    assert out == f"Оболочка из {red}кордита{reset} слаба.", repr(out)
    assert transfer.decode_manual("‹2› до ‹1›", f"a{red}b{reset}") == f"{reset} до {red}"
    try:
        transfer.decode_manual("без кодов", f"a{red}b")
        raise AssertionError("ручная строка без кода прошла")
    except ValueError:
        pass
    print("formats: synthetic ok")


def real():
    if not os.path.isdir(ROMFS):
        print("formats: work/romfs нет — проверки на данных игры пропущены")
        return
    import font
    import pak
    for p in glob.glob(os.path.join(ROMFS, "**", "*.pak"), recursive=True):
        b = open(p, "rb").read()
        for t, g, v, off, us, cs in pak.resources(b):
            if t == "FONT":
                font.Font(lzss.unpack_asset(b[off:off + cs], us) if cs != us else b[off:off + cs])
    import pakwrite
    for p in glob.glob(os.path.join(ROMFS, "**", "*.pak"), recursive=True):
        b = open(p, "rb").read()
        assert pakwrite.rebuild(b) == b, f"пересборка без замен меняет {p}"
    out, report = transfer.transfer(ROMFS)
    assert len(out) >= MIN_AUTO, f"по-русски {len(out)} строк, было {MIN_AUTO}"
    assert not report, f"без перевода {len(report)} строк: {[r[0] for r in report][:5]}"
    print(f"formats: fonts ok, transfer {len(out)} строк, ручных {len(report)}")


if __name__ == "__main__":
    synthetic()
    real()
