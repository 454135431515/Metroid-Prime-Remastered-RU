"""Пересборка архива Remastered (`.pak`) с заменёнными ресурсами.

Устройство (R4): RFRM «PACK» (32 байта) → RFRM «TOCC» (32 байта) с блоками ADIR (каталог: u32 n,
записи по 52 байта: тип, GUID, две версии, u64 смещение от начала файла, u64 распакованный,
u64 сжатый размер), META (u32 n, записи GUID + u32 смещение на u32 длину, метаданные выровнены
по 4 байта), STRG (имена) — подряд, с 24-байтными заголовками (4cc, u64 размер, 12 байт);
затем ресурсы подряд, без выравнивания; файл добит нулями до кратного 32. Один ресурс может быть
записан в каталоге дважды (то же смещение) — такие записи указывают на один кусок.

Без замен пересборка даёт исходный файл байт в байт (test_formats).
"""

import struct

import pak


def _toc(b):
    """(начало данных TOCC, [(4cc, начало данных, конец, сырой заголовок 24 байта)])."""
    assert b[:4] == b"RFRM" and b[20:24] == b"PACK" and b[32:36] == b"RFRM" and b[52:56] == b"TOCC"
    size, = struct.unpack_from("<Q", b, 36)
    out, p, end = [], 64, 64 + size
    while p < end:
        k = b[p:p + 4]
        n, = struct.unpack_from("<Q", b, p + 4)
        out.append((k, p + 24, p + 24 + n, b[p:p + 24]))
        p += 24 + n
    assert p == end
    return end, out


def rebuild(b, assets=None, metas=None):
    """Новый архив. assets: {guid hex: (данные как в архиве, распакованный размер)};
    metas: {guid hex: новые метаданные}."""
    assets, metas = assets or {}, metas or {}
    toc_end, toc = _toc(b)
    rs = pak.resources(b)
    by_guid = {r[1] for r in rs}
    for g in list(assets) + list(metas):
        if g not in by_guid:
            raise KeyError(f"в архиве нет ресурса {g}")

    # META: та же таблица, метаданные заново, по 4 байта
    meta_body = None
    for k, s, e, hdr in toc:
        if k == b"META":
            n, = struct.unpack_from("<I", b, s)
            rows = [(b[s + 4 + 20 * i:s + 20 + 20 * i].hex(), struct.unpack_from("<I", b, s + 20 + 20 * i)[0])
                    for i in range(n)]
            base = 4 + 20 * n
            blobs, at = bytearray(), {}
            # метаданные — в исходном порядке файла; у дубля ресурса своя копия (своё смещение)
            for g, off in sorted(set(rows), key=lambda r: r[1]):
                ln, = struct.unpack_from("<I", b, s + off)
                data = metas.get(g, b[s + off + 4:s + off + 4 + ln])
                while (base + len(blobs)) % 4:
                    blobs.append(0)
                at[(g, off)] = base + len(blobs)
                blobs += struct.pack("<I", len(data)) + data
            while (base + len(blobs)) % 4:  # блок тоже выровнен по 4
                blobs.append(0)
            table = bytearray(struct.pack("<I", n))
            for g, off in rows:
                table += bytes.fromhex(g) + struct.pack("<I", at[(g, off)])
            meta_body = bytes(table + blobs)

    # оглавление с новым META; ADIR — той же длины, заполняется после раскладки ресурсов
    parts, adir_at = [], None
    pos = 64
    for k, s, e, hdr in toc:
        body = meta_body if k == b"META" else b[s:e]
        h = bytearray(hdr)
        struct.pack_into("<Q", h, 4, len(body))
        if k == b"ADIR":
            adir_at = pos + 24
        parts.append(bytes(h) + body)
        pos += 24 + len(body)
    toc_data = b"".join(parts)
    head = bytearray(b[:64])
    struct.pack_into("<Q", head, 36, len(toc_data))
    out = bytearray(head + toc_data)

    # ресурсы подряд в исходном порядке; изменённые — новыми данными
    ranges = sorted({(r[3], r[5]) for r in rs})
    first = ranges[0][0]
    assert first == toc_end, (first, toc_end)
    replaced = {}
    for r in rs:
        if r[1] in assets:
            replaced[(r[3], r[5])] = assets[r[1]][0]
    new_off, cursor = {}, first
    for off, size in ranges:
        if off < cursor:  # дубль внутри уже записанного куска — их нет, кроме одинаковых смещений
            raise ValueError(f"ресурс {off} перекрывает предыдущий")
        out += b[cursor:off]  # зазор (в данных игры его нет)
        new_off[(off, size)] = len(out)
        out += replaced.get((off, size), b[off:off + size])
        cursor = off + size
    tail = b[cursor:struct.unpack_from("<Q", b, 4)[0] + 32]
    out += tail
    struct.pack_into("<Q", out, 4, len(out) - 32)
    while len(out) % 32:
        out.append(0)

    # ADIR: новые смещения и размеры
    n, = struct.unpack_from("<I", out, adir_at)
    for i in range(n):
        p = adir_at + 4 + 52 * i
        g = out[p + 4:p + 20].hex()
        off, usize, csize = struct.unpack_from("<QQQ", out, p + 28)
        struct.pack_into("<Q", out, p + 28, new_off[(off, csize)])
        if g in assets:
            data, us = assets[g]
            struct.pack_into("<QQ", out, p + 36, us, len(data))
    return bytes(out)
