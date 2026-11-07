"""Тексты Remastered: ресурс MSBT (RFRM) с блоками по языкам, в каждом — MsgStdBn Nintendo.

    python -I tools/msbt.py <файл.pak> [язык]     # метки и строки языка (по умолчанию USEN)

Обёртка: RFRM «MSBT», затем блоки <язык 4cc> <размер u64> <8 байт>, внутри — MsgStdBn
(little-endian, UTF-16): LBL1 — хеш-таблица меток (индекс строки), ATR1, TXT2 — смещения
и строки. Управляющие коды в тексте (0x0E …) сохраняются как есть.
"""

import struct
import sys


def lang_blocks(res):
    """{язык: (начало MsgStdBn, конец)} внутри ресурса MSBT (RFRM)."""
    assert res[:4] == b"RFRM" and res[20:24] == b"MSBT", res[:24]
    out, p = {}, 32
    while p + 24 <= len(res):
        lang = res[p:p + 4].decode("ascii")
        size, = struct.unpack_from("<Q", res, p + 4)
        out[lang] = (p + 24, p + 24 + size)
        p += 24 + size
    return out


def sections(m):
    assert m[:8] == b"MsgStdBn" and m[8:10] == b"\xff\xfe", m[:10]
    n, = struct.unpack_from("<H", m, 0x0E)
    out, p = {}, 0x20
    for _ in range(n):
        name = m[p:p + 4].decode()
        size, = struct.unpack_from("<I", m, p + 4)
        out[name] = m[p + 16:p + 16 + size]
        p += 16 + size
        p = (p + 15) & ~15
    return out


def parse(m):
    """[(метка, текст)] в порядке индексов строк; текст — str с управляющими кодами."""
    s = sections(m)
    lbl, txt = s["LBL1"], s["TXT2"]
    nb, = struct.unpack_from("<I", lbl, 0)
    labels = {}
    for i in range(nb):
        cnt, off = struct.unpack_from("<II", lbl, 4 + 8 * i)
        p = off
        for _ in range(cnt):
            ln = lbl[p]
            name = lbl[p + 1:p + 1 + ln].decode()
            idx, = struct.unpack_from("<I", lbl, p + 1 + ln)
            labels[idx] = name
            p += 1 + ln + 4
    nt, = struct.unpack_from("<I", txt, 0)
    offs = list(struct.unpack_from(f"<{nt}I", txt, 4)) + [len(txt)]
    texts = [txt[offs[i]:offs[i + 1]].decode("utf-16-le").rstrip("\0") for i in range(nt)]
    return [(labels.get(i, f"#{i}"), t) for i, t in enumerate(texts)]


if __name__ == "__main__":
    sys.path.insert(0, __import__("os").path.dirname(__file__))
    import pak
    b = open(sys.argv[1], "rb").read()
    want = sys.argv[2] if len(sys.argv) > 2 else "USEN"
    for t, g, v, off, us, cs in pak.resources(b):
        if t != "MSBT":
            continue
        res = b[off:off + cs]
        langs = lang_blocks(res)
        s, e = langs[want]
        rows = parse(res[s:e])
        print(f"== {g}  языки: {' '.join(langs)}  строк: {len(rows)}")
        for label, text in rows[:3]:
            print(f"  {label}: {text[:100]!r}")
