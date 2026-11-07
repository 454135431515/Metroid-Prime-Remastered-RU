"""RomFS игры из NSP (свой дамп + ключи консоли владельца): список файлов и извлечение.

    python -I tools/nsp_romfs.py <игра.nsp> <prod.keys> list [фильтр]
    python -I tools/nsp_romfs.py <игра.nsp> <prod.keys> extract <папка> [фильтр]

NSP — контейнер PFS0 с NCA и билетом (.tik). Билет даёт ключ title (зашифрован titlekek
поколения ключей NCA); заголовок NCA расшифровывается AES-XTS ключом header_key (сектор 0x200,
номер сектора big-endian); раздел RomFS — AES-CTR. Внутри раздела — IVFC, последний уровень —
сам RomFS (таблицы каталогов и файлов). Ключи читаются из prod.keys и не выводятся.
"""

import os
import struct
import sys

from Crypto.Cipher import AES
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def load_keys(path):
    keys = {}
    for line in open(path, encoding="utf-8"):
        if "=" in line:
            k, v = (x.strip() for x in line.split("=", 1))
            keys[k] = bytes.fromhex(v)
    return keys


def pfs0(f, base=0):
    f.seek(base)
    magic, n, strsize, _ = struct.unpack("<4sIII", f.read(16))
    if magic != b"PFS0":
        raise ValueError("не PFS0")
    entries = [struct.unpack("<QQII", f.read(24)) for _ in range(n)]
    names = f.read(strsize)
    data = base + 16 + 24 * n + strsize
    out = {}
    for off, size, name_off, _ in entries:
        name = names[name_off:names.index(b"\0", name_off)].decode()
        out[name] = (data + off, size)
    return out


def xts_decrypt(key, data, sector_size=0x200, first=0):
    out = bytearray()
    for i in range(0, len(data), sector_size):
        tweak = (first + i // sector_size).to_bytes(16, "big")
        d = Cipher(algorithms.AES(key), modes.XTS(tweak)).decryptor()
        out += d.update(data[i:i + sector_size]) + d.finalize()
    return bytes(out)


class Nca:
    def __init__(self, f, offset, keys, title_keys):
        self.f, self.offset = f, offset
        f.seek(offset)
        h = xts_decrypt(keys["header_key"], f.read(0xC00))
        if h[0x200:0x204] != b"NCA3":
            raise ValueError("заголовок NCA не расшифрован (не тот header_key?)")
        self.h = h
        self.content_type = h[0x205]
        gen = max(h[0x206], h[0x220])
        gen = gen - 1 if gen else 0
        rights = h[0x230:0x240]
        if any(rights):
            enc = title_keys.get(rights)
            if enc is None:
                raise ValueError("нет билета для rights id")
            self.key = AES.new(keys[f"titlekek_{gen:02x}"], AES.MODE_ECB).decrypt(enc)
        else:  # область ключей NCA (0x300), ключ CTR — третий; шифрована key_area_key по индексу 0x207
            kak = keys[f"key_area_key_{('application', 'ocean', 'system')[h[0x207]]}_{gen:02x}"]
            self.key = AES.new(kak, AES.MODE_ECB).decrypt(h[0x300:0x340])[0x20:0x30]
        self.sections = []
        for i in range(4):
            start, end = struct.unpack_from("<II", h, 0x240 + 16 * i)
            if end:
                self.sections.append((i, start * 0x200, end * 0x200, h[0x400 + 0x200 * i:0x600 + 0x200 * i]))

    def read(self, sec, rel, size):
        """size байт раздела sec с относительного смещения rel (AES-CTR)."""
        i, start, end, fsh = sec
        if fsh[4] != 3:
            raise ValueError(f"раздел {i}: шифрование {fsh[4]}, ожидалось CTR")
        absolute = start + rel
        aligned = absolute & ~0xF
        skip = absolute - aligned
        self.f.seek(self.offset + aligned)
        raw = self.f.read(skip + size)
        ctr = fsh[0x140:0x148][::-1] + (aligned >> 4).to_bytes(8, "big")
        dec = AES.new(self.key, AES.MODE_CTR, nonce=b"", initial_value=ctr).decrypt(raw)
        return dec[skip:skip + size]


class RomFs:
    def __init__(self, nca, sec):
        fsh = sec[3]
        if fsh[2] != 0 or fsh[8:12] != b"IVFC":
            raise ValueError("раздел не RomFS")
        lvl6 = struct.unpack_from("<QQ", fsh, 0x8 + 0x10 + 0x18 * 5)  # последний уровень IVFC — данные
        self.nca, self.sec, self.base = nca, sec, lvl6[0]
        hdr = struct.unpack("<10Q", self.rd(0, 0x50))
        _, _, _, dir_off, dir_size, _, _, file_off, file_size, data_off = hdr
        self.dirs = self.rd(dir_off, dir_size)
        self.files = self.rd(file_off, file_size)
        self.data = data_off

    def rd(self, off, size):
        return self.nca.read(self.sec, self.base + off, size)

    def walk(self, d=0, prefix=""):
        parent, sibling, child, file, _, nlen = struct.unpack_from("<6I", self.dirs, d)
        name = self.dirs[d + 0x18:d + 0x18 + nlen].decode()
        path = f"{prefix}/{name}" if d else ""
        f = file
        while f != 0xFFFFFFFF:
            _, fsib, off, size, _, fl = struct.unpack_from("<IIQQII", self.files, f)
            yield f"{path}/{self.files[f + 0x20:f + 0x20 + fl].decode()}", off, size
            f = fsib
        c = child
        while c != 0xFFFFFFFF:
            yield from self.walk(c, path)
            c = struct.unpack_from("<I", self.dirs, c + 4)[0]

    def read_file(self, off, size):
        return self.rd(self.data + off, size)


def open_romfs(nsp_path, keys_path):
    keys = load_keys(keys_path)
    f = open(nsp_path, "rb")
    files = pfs0(f)
    title_keys = {}
    for name, (off, size) in files.items():
        if name.endswith(".tik"):
            f.seek(off)
            t = f.read(size)
            title_keys[t[0x2A0:0x2B0]] = t[0x180:0x190]
    best = None
    for name, (off, size) in files.items():
        if name.endswith(".nca") and not name.endswith(".cnmt.nca"):
            nca = Nca(f, off, keys, title_keys)
            if nca.content_type == 0 and (best is None or size > best[1]):  # 0 — программа
                best = (nca, size)
    nca = best[0]
    for sec in nca.sections:
        if sec[3][2] == 0 and sec[3][8:12] == b"IVFC":
            return RomFs(nca, sec)
    raise ValueError("в программном NCA нет RomFS")


def main(nsp, keys, cmd, *rest):
    rom = open_romfs(nsp, keys)
    flt = (rest[1] if cmd == "extract" and len(rest) > 1 else rest[0] if cmd == "list" and rest else "")
    entries = [e for e in rom.walk() if flt in e[0]]
    if cmd == "list":
        for path, off, size in entries:
            print(f"{size:12d}  {path}")
        print(f"{len(entries)} файлов, {sum(e[2] for e in entries) / 2**20:.1f} МиБ")
    elif cmd == "extract":
        out = rest[0]
        for path, off, size in entries:
            dst = os.path.join(out, path.lstrip("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, "wb").write(rom.read_file(off, size))
        print(f"извлечено {len(entries)} файлов -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
