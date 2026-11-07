"""Текстуры Remastered (TXTR) — только то, что нужно атласу шрифта: формат 0 (R8), один слой,
один мип. Чтение и запись поверхности Tegra X1 block linear.

Ресурс в архиве: RFRM «TXTR» (HEAD — заголовок, GPU — данные). Где в нём лежат куски
поверхности и как они сжаты, говорят метаданные из блока META архива (STextureMetaData):
28 байт заголовка (размер поверхности по смещению 20, число чтений по 24), чтения
(байт индекс, u32 смещение, u32 размер — от начала ресурса) и буферы (u32 индекс, смещение
в чтении, размер, смещение в поверхности, размер в поверхности). Буфер — u32 режим сжатия и
данные (0 — как есть, 1–3 — LZSS, tools/lzss.py).

Block linear (tegra_swizzle 0.3.2): GOB — 64 байта × 8 строк (512 байт); высота блока в GOB
выбирается по высоте текстуры; блоки идут строками, внутри GOB — фиксированная перестановка.
"""

import struct

import lzss


def head(asset):
    """(kind, format, width, height, layers, tile, swizzle, [размеры мипов]) и смещение HEAD."""
    assert asset[:4] == b"RFRM" and asset[20:24] == b"TXTR"
    p = 32
    assert asset[p:p + 4] == b"HEAD", asset[p:p + 4]
    s = p + 24
    kind, fmt, w, h, layers, tile, swz, nm = struct.unpack_from("<8I", asset, s)
    return (kind, fmt, w, h, layers, tile, swz, list(struct.unpack_from(f"<{nm}I", asset, s + 32))), s


def parse_meta(m):
    size, nreads = struct.unpack_from("<II", m, 20)
    p, reads = 28, {}
    for _ in range(nreads):
        idx, off, sz = struct.unpack_from("<BII", m, p)
        reads[idx] = (off, sz)
        p += 9
    nbuf, = struct.unpack_from("<I", m, p)
    p += 4
    bufs = [struct.unpack_from("<5I", m, p + 20 * i) for i in range(nbuf)]
    return size, reads, bufs, m[:20]


def surface(asset, meta):
    size, reads, bufs, _ = parse_meta(meta)
    out = bytearray(size)
    for idx, off, sz, dst, dsz in bufs:
        roff, _ = reads[idx]
        blob = asset[roff + off:roff + off + sz]
        out[dst:dst + dsz] = lzss.unpack_asset(blob, dsz)
    return bytes(out)


def block_height(rows):
    hh = rows + rows // 2
    for limit, bh in ((128, 16), (64, 8), (32, 4), (16, 2)):
        if hh >= limit:
            return bh
    return 1


def _addresses(width, height, bh):
    """Смещение каждого байта (x, y) в поверхности, построчно; и размер поверхности."""
    gobs_w = (width + 63) // 64
    block_rows = 8 * bh
    rows_blocks = (height + block_rows - 1) // block_rows
    addr = []
    for y in range(height):
        base_y = (y // block_rows) * 512 * bh * gobs_w + ((y % block_rows) // 8) * 512
        yy = y % 8
        part_y = (yy // 2) * 64 + (yy % 2) * 16
        for x in range(width):
            xx = x % 64
            addr.append(base_y + (x // 64) * 512 * bh + (xx // 32) * 256 + part_y + ((xx % 32) // 16) * 32 + (xx % 16))
    return addr, rows_blocks * 512 * bh * gobs_w


def deswizzle(surf, width, height):
    addr, _ = _addresses(width, height, block_height(height))
    return bytes(surf[a] for a in addr)


def swizzle(pixels, width, height):
    addr, size = _addresses(width, height, block_height(height))
    out = bytearray(size)
    for i, a in enumerate(addr):
        out[a] = pixels[i]
    return bytes(out)


def decode_r8(asset, meta):
    (kind, fmt, w, h, layers, *_), _ = head(asset)
    if fmt != 0 or layers != 1:
        raise ValueError(f"не R8 одного слоя: формат {fmt}, слоёв {layers}")
    return w, h, deswizzle(surface(asset, meta), w, h)
