"""Текст Remastered и перевода GameCube: разбиение на коды и куски текста.

Коды MSBT: U+000E, группа (u16), тип (u16), длина параметров в байтах (u16), параметры
(в строке UTF-16 — длина/2 символов); U+000F, группа, тип — закрывающий тег. Остальное — текст
(включая «{0}» — подстановки игры и «\\n»).
Теги GameCube: «&имя;» или «&имя=значение;» (tools/strg.py перевода GameCube).
"""

import re

GC_TAG = re.compile(r"&[a-z-]+(?:=[^;]*)?;")


def rm_tokens(s):
    """[(«code»|«text», строка)] для строки Remastered."""
    out, i, buf = [], 0, []
    while i < len(s):
        c = s[i]
        if c == "\x0e":
            if buf:
                out.append(("text", "".join(buf)))
                buf = []
            n = ord(s[i + 3]) // 2
            out.append(("code", s[i:i + 4 + n]))
            i += 4 + n
        elif c == "\x0f":
            if buf:
                out.append(("text", "".join(buf)))
                buf = []
            out.append(("code", s[i:i + 3]))
            i += 3
        else:
            buf.append(c)
            i += 1
    if buf:
        out.append(("text", "".join(buf)))
    return out


def gc_tokens(s):
    out, pos = [], 0
    for m in GC_TAG.finditer(s):
        if m.start() > pos:
            out.append(("text", s[pos:m.start()]))
        out.append(("code", m.group()))
        pos = m.end()
    if pos < len(s):
        out.append(("text", s[pos:]))
    return out


def texts(tokens):
    return [t for k, t in tokens if k == "text"]


def code_kind(code):
    """Грубый вид кода Remastered для сверки: (группа, тип)."""
    if code[0] == "\x0e":
        return (ord(code[1]), ord(code[2]))
    return ("close", ord(code[1]), ord(code[2]))
