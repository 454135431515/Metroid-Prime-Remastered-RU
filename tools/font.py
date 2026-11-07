"""Шрифты Remastered с кириллицей: ресурс FONT и его атлас TXTR.

    python -I tools/font.py <архив.pak> <out_dir> [preview.png]

FONT (RFRM): 32 байта заголовка, затем текстуры (u32 n, GUID×n), u32, размеры (u32 n, u32×n),
отступы (u32 n, f32×n — первый = pad поля расстояний), метрики (u32 n, 16×n), u32 число
глифов, u32, записи глифов: u16 символ, u16 начертание, 3 байта, u8 текстура, 9 f32 (left, top,
width, height, u0, v0, u1, v1, advance), u32 число пар кернинга, пары по 6 байт.
Начертание 0, текстура 0 — латиница на атласе textures[0] (R8, поле расстояний, 53/255 на
тексел — как у порта Odrannnn). Записи не отсортированы: игра индексирует их при загрузке,
русские дописываются в конец.

Кириллица строится генератором HD-шрифта перевода GameCube (MP russian/tools/hd_font.py,
рецепты tools/cyrillic.py) — латиница этого же атласа уже проверена в TR2: атлас дорастает
полками снизу, у старых глифов пересчитываются v. Атлас пишется обратно в раскладке Tegra,
сжатый LZSS режима 3, как в игре.
"""

import os
import struct
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(HERE, "..", "..", "MP russian", "tools"))
import cyrillic  # noqa: E402
import hd_font  # noqa: E402
import lzss  # noqa: E402
import pak  # noqa: E402
import txtr  # noqa: E402

PER_PIXEL = 53 / 255


class Font:
    def __init__(self, d):
        assert d[:4] == b"RFRM" and d[20:24] == b"FONT", d[:24]
        self.d = d
        at = 0x20
        nt, = struct.unpack_from("<I", d, at)
        self.textures = [d[at + 4 + 16 * i:at + 20 + 16 * i].hex() for i in range(nt)]
        at += 4 + 16 * nt + 4
        ns, = struct.unpack_from("<I", d, at)
        at += 4 + 4 * ns
        npd, = struct.unpack_from("<I", d, at)
        self.pad, = struct.unpack_from("<f", d, at + 4)
        at += 4 + 4 * npd
        nm, = struct.unpack_from("<I", d, at)
        at += 4 + 16 * nm
        self.count_at = at
        n, = struct.unpack_from("<I", d, at)
        at += 8
        self.records = []  # [bytearray записи 44 байта, байты пар]
        for _ in range(n):
            np_, = struct.unpack_from("<I", d, at + 44)
            self.records.append([bytearray(d[at:at + 44]), d[at + 44:at + 48 + 6 * np_]])
            at += 48 + 6 * np_
        if at != len(d):
            raise ValueError(f"FONT: разобрано {at} из {len(d)} байт")

    def latin(self):
        """Записи начертания 0 на текстуре 0: [(запись, символ, 9 f32)]."""
        out = []
        for rec in self.records:
            ch, face = struct.unpack_from("<HH", rec[0], 0)
            if face == 0 and rec[0][7] == 0:
                out.append((rec, ch, list(struct.unpack_from("<9f", rec[0], 8))))
        return out

    def build(self):
        body = bytearray(self.d[:self.count_at])
        body += struct.pack("<I", len(self.records)) + self.d[self.count_at + 4:self.count_at + 8]
        for rec, pairs in self.records:
            body += rec + pairs
        struct.pack_into("<Q", body, 4, len(body) - 32)
        return bytes(body)


def txtr_asset(old, meta, width, height, pixels):
    """Новый ресурс TXTR (R8 width×height) и его метаданные на месте старых."""
    (kind, fmt, w, h, layers, tile, swz, mips), hs = txtr.head(old)
    assert fmt == 0 and layers == 1 and len(mips) == 1, (fmt, layers, mips)
    surf = txtr.swizzle(pixels, width, height)
    gpu = struct.pack("<I", 3) + lzss.compress(3, surf)
    head_hdr = old[32:56]
    head_body = bytearray(old[56:56 + struct.unpack_from("<Q", old, 36)[0]])
    struct.pack_into("<II", head_body, 8, width, height)
    struct.pack_into("<I", head_body, 32, width * height)
    gpu_at = 56 + len(head_body)
    gpu_hdr = bytearray(old[gpu_at:gpu_at + 24])
    assert gpu_hdr[:4] == b"GPU ", gpu_hdr[:4]
    struct.pack_into("<Q", gpu_hdr, 4, len(gpu))
    hdr = bytearray(head_hdr)
    struct.pack_into("<Q", hdr, 4, len(head_body))
    asset = bytearray(old[:32]) + hdr + head_body + gpu_hdr + gpu
    struct.pack_into("<Q", asset, 4, len(asset) - 32)
    size, reads, bufs, hdr20 = txtr.parse_meta(meta)
    assert len(reads) == 1 and len(bufs) == 1, (reads, bufs)
    idx, off, _, dst, _ = bufs[0]
    assert off == gpu_at + 24, (off, gpu_at)
    new_meta = (hdr20 + struct.pack("<II", len(surf), 1) + struct.pack("<BII", idx, 0, len(asset))
                + struct.pack("<I", 1) + struct.pack("<5I", idx, off, len(gpu), 0, len(surf)) + meta[28 + 9 + 4 + 20:])
    return bytes(asset), new_meta


def cyrillize(font_bytes, atlas_asset, atlas_meta, preview=None):
    """(новый FONT, новый TXTR, новые метаданные TXTR, добавлено глифов)."""
    font = Font(font_bytes)
    w, h, px = txtr.decode_r8(atlas_asset, atlas_meta)
    lat = font.latin()
    work = tempfile.mkdtemp(prefix="font-", dir=os.path.join(HERE, "..", "work"))
    src, dst = os.path.join(work, "src.sdfont"), os.path.join(work, "dst.sdfont")
    seen = {}
    for rec, ch, f in lat:
        seen.setdefault(ch, [ch] + f)
    hd_font.write(src, w, h, font.pad, PER_PIXEL, list(seen.values()),
                  np.frombuffer(px, np.uint8).reshape(h, w))
    hd_font.build(src, dst, preview)
    nw, nh, _, _, glyphs, dist = hd_font.read(dst)
    assert nw == w
    by = {g[0]: g for g in glyphs}
    for rec, ch, _ in lat:  # старые глифы: v пересчитаны под новую высоту
        struct.pack_into("<9f", rec[0], 8, *by[ch][1:])
    template = {ch: rec[0] for rec, ch, _ in lat}
    recipes = {**cyrillic.CAPITALS, **cyrillic.LOWERCASE}
    added = 0
    for g in glyphs:
        ch = g[0]
        if ch in template:
            continue
        ref = recipes.get(chr(ch), ("A",))[0]
        rec = bytearray(template.get(ord(ref), template[ord("A")]))
        struct.pack_into("<HH", rec, 0, ch, 0)
        rec[7] = 0
        struct.pack_into("<9f", rec, 8, *g[1:])
        font.records.append([rec, struct.pack("<I", 0)])
        added += 1
    asset, meta = txtr_asset(atlas_asset, atlas_meta, nw, nh, dist.tobytes())
    return font.build(), asset, meta, added


if __name__ == "__main__":
    pak_path, out = sys.argv[1], sys.argv[2]
    b = open(pak_path, "rb").read()
    rs = {r[1]: r for r in pak.resources(b)}
    metas = pak.meta_table(b)
    for t, g, v, off, us, cs in pak.resources(b):
        if t != "FONT":
            continue
        fb = lzss.unpack_asset(b[off:off + cs], us) if cs != us else b[off:off + cs]
        tex = Font(fb).textures[0]
        r = rs[tex]
        nf, na, nm, added = cyrillize(fb, b[r[3]:r[3] + r[5]], metas[tex], sys.argv[3] if len(sys.argv) > 3 else None)
        os.makedirs(out, exist_ok=True)
        for name, data in ((f"{g}.FONT", nf), (f"{tex}.TXTR", na), (f"{tex}.meta", nm)):
            open(os.path.join(out, name), "wb").write(data)
        print(f"FONT {g[:8]}: +{added} глифов, атлас {tex[:8]}")
