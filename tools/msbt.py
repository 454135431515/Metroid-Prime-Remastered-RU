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


def build(m, texts):
    """MsgStdBn заново: LBL1, ATR1 и прочие секции как есть, TXT2 — строки texts (по индексу).
    Секции: 4cc, u32 размер, 8 байт, данные, добивка 0xAB до 16; размер файла — u32 по 0x12."""
    assert m[:8] == b"MsgStdBn" and m[8:10] == b"\xff\xfe", m[:10]
    n, = struct.unpack_from("<H", m, 0x0E)
    out = bytearray(m[:0x20])
    p = 0x20
    for _ in range(n):
        name = m[p:p + 4]
        size, = struct.unpack_from("<I", m, p + 4)
        hdr = bytearray(m[p:p + 16])
        data = m[p + 16:p + 16 + size]
        if name == b"TXT2":
            count, = struct.unpack_from("<I", data, 0)
            if count != len(texts):
                raise ValueError(f"TXT2: {count} строк, дано {len(texts)}")
            strs = [(t + "\0").encode("utf-16-le") for t in texts]
            offs, at = [], 4 + 4 * count
            for s in strs:
                offs.append(at)
                at += len(s)
            data = struct.pack(f"<I{count}I", count, *offs) + b"".join(strs)
            struct.pack_into("<I", hdr, 4, len(data))
        out += hdr + data
        while len(out) % 16:
            out.append(0xAB)
        p = (p + 16 + size + 15) & ~15
    struct.pack_into("<I", out, 0x12, len(out))
    return bytes(out)


def build_resource(res, langs):
    """Ресурс MSBT (RFRM) с заменёнными языковыми блоками: langs = {язык: MsgStdBn}."""
    blocks = lang_blocks(res)
    out = bytearray(res[:32])
    p = 32
    for lang, (s, e) in blocks.items():
        hdr = bytearray(res[s - 24:s])
        body = langs.get(lang, res[s:e])
        struct.pack_into("<Q", hdr, 4, len(body))
        out += hdr + body
        p = e
    out += res[p:]
    struct.pack_into("<Q", out, 4, len(out) - 32)
    return bytes(out)
