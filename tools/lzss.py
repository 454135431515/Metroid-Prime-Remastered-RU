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


def compress(mode, data):
    """Обратное к decompress: жадный поиск самого длинного совпадения группами (как пишет игра,
    байт в байт не обязательно — проверяется распаковкой). Длина данных кратна группе."""
    g = 1 << (mode - 1)
    if len(data) % g:
        raise ValueError("длина не кратна группе")
    groups = [data[i:i + g] for i in range(0, len(data), g)]
    max_count = 15 + (4 - mode)
    min_count = 4 - mode
    if min_count < 1:
        min_count = 1
    seen = {}
    out = bytearray()
    flags_pos, nflags, flags = None, 8, 0
    i = 0

    def put_flag(bit, payload):
        nonlocal flags_pos, nflags, flags
        if nflags == 8:
            if flags_pos is not None:
                out[flags_pos] = flags
            flags_pos, nflags, flags = len(out), 0, 0
            out.append(0)
        flags |= bit << (7 - nflags)
        nflags += 1
        out.extend(payload)

    while i < len(groups):
        best_len, best_dist = 0, 0
        for j in reversed(seen.get(groups[i], ())[-64:]):
            dist = i - j
            if dist > 4095:
                break
            n = 0
            while n < max_count and i + n < len(groups) and groups[j + n] == groups[i + n]:
                n += 1
            if n > best_len:
                best_len, best_dist = n, dist
                if n == max_count:
                    break
        if best_len >= max(min_count, 2 if mode == 1 else 1) and best_len * g > 2:
            c = best_len - (4 - mode)
            put_flag(1, bytes([(c << 4) | (best_dist >> 8), best_dist & 0xFF]))
            step = best_len
        else:
            put_flag(0, groups[i])
            step = 1
        for k in range(step):
            seen.setdefault(groups[i + k], []).append(i + k)
        i += step
    if flags_pos is not None:
        out[flags_pos] = flags
    return bytes(out)
