"""LZSS ресурсов Remastered (как retrotool util/lzss.rs и port_remastered_lzss.h порта).

Режим — log2 размера группы + 1 (1, 2, 3 → группы по 1, 2, 4 байта). Байт заголовка на 8 групп:
бит 0 — группа копируется как есть, бит 1 — ссылка назад (2 байта: счётчик в старшей тетраде,
расстояние в 12 битах, в группах).
"""


def decompress(mode, data, out_size):
    if mode not in (1, 2, 3):
        raise ValueError(f"режим LZSS {mode}")
    g = 1 << (mode - 1)
    out = bytearray()
    i = 0
    header = 0
    left = 0
    while i < len(data) and len(out) < out_size:
        if left == 0:
            header, left, i = data[i], 8, i + 1
        if header & 0x80 == 0:
            out += data[i:i + g]
            i += g
        else:
            count = (data[i] >> 4) + (4 - mode)
            dist = ((data[i] & 0x0F) * 256 + data[i + 1]) << (mode - 1)
            i += 2
            if dist == 0 or dist > len(out):
                raise ValueError("LZSS: ссылка за начало")
            for _ in range(count * g):
                out.append(out[-dist])
        header = (header << 1) & 0xFF
        left -= 1
    if len(out) != out_size:
        raise ValueError(f"LZSS: {len(out)} байт вместо {out_size}")
    return bytes(out)


def unpack_asset(blob, out_size):
    """Ресурс из архива: u32 режим, затем данные (0 — без сжатия)."""
    mode = int.from_bytes(blob[:4], "little")
    if mode == 0:
        return blob[4:4 + out_size]
    return decompress(mode, blob[4:], out_size)
