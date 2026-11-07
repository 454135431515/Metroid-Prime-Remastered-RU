"""Архивы ресурсов Remastered (`.pak`): RFRM «PACK» с таблицей ADIR.

    python -I tools/pak.py <файл.pak> [тип]     # список ресурсов: тип, GUID, размеры

Блок RFRM: magic, размер данных (u64), 8 байт, тип (4cc), версия, ещё версия; дочерние блоки —
внутри данных. В PACK: TOCC (оглавление) с блоками ADIR (каталог ресурсов), META, STRG
(имена) и др. Запись ADIR: тип 4cc, GUID 16 байт, две версии u32, смещение, размер
распакованный, размер сжатый (u64).
"""

import struct
import sys


def chunks(b, pos, end):
    """[(тип, начало данных, конец данных)] блоков RFRM-подобного формата."""
    out = []
    while pos + 20 <= end:
        magic = b[pos:pos + 4]
        if magic == b"RFRM":
            size, = struct.unpack_from("<Q", b, pos + 4)
            kind = b[pos + 20:pos + 24]
            out.append((kind, pos + 32, pos + 32 + size))
            pos += 32 + size
        else:
            size, = struct.unpack_from("<Q", b, pos + 4)
            out.append((magic, pos + 24, pos + 24 + size))
            pos += 24 + size
    return out


def resources(b):
    """[(тип, guid hex, версия, смещение, распакованный, сжатый)] из ADIR."""
    top = chunks(b, 0, len(b))
    kind, s, e = top[0]
    assert kind == b"PACK", kind
    out = []
    for k, cs, ce in chunks(b, s, e):
        if k == b"TOCC":
            for k2, s2, e2 in chunks(b, cs, ce):
                if k2 == b"ADIR":
                    n, = struct.unpack_from("<I", b, s2)
                    p = s2 + 4
                    for _ in range(n):
                        t = b[p:p + 4].decode("ascii", "replace")
                        guid = b[p + 4:p + 20]
                        v1, v2, off, usize, csize = struct.unpack_from("<IIQQQ", b, p + 20)
                        out.append((t, guid.hex(), v1, off, usize, csize))
                        p += 52
    return out


if __name__ == "__main__":
    data = open(sys.argv[1], "rb").read()
    rs = resources(data)
    want = sys.argv[2] if len(sys.argv) > 2 else None
    from collections import Counter
    if want:
        for r in rs:
            if r[0] == want:
                print(*r)
    else:
        for t, n in Counter(r[0] for r in rs).most_common():
            print(t, n)
        print(len(rs), "ресурсов")
