"""Перевод GameCube → строки Remastered.

    python -I tools/transfer.py <папка с .pak> [отчёт.tsv]

Метка строки Remastered `[XXXXXXXX]_NNN` = таблица STRG GameCube и индекс: русский берётся из
MP russian/text/ru.json (единственный источник перевода). Ручные строки — text/ru-remastered.json
{метка: русский}, в них коды Remastered записаны как «&rm=<hex UTF-16>;».

Правила для строки из ru.json:
- переносы, добавленные переводом под узкие поля GameCube (в английском GameCube их нет): перенос
  слова «Мерцаю-\\nщая» склеивается, настоящий дефис «Пират-\\nневидимка» остаётся без переноса —
  решает словарь слов остального перевода; не решилось — строка в отчёт;
- если в Remastered переносов нет, а в GameCube были — одиночные переносы становятся пробелами;
- коды Remastered (цвет, значки кнопок) остаются на местах, куски текста между ними заменяются
  кусками русской строки по порядку; если число кусков не совпало — строка остаётся английской
  и уходит в отчёт (её переводят в text/ru-remastered.json).
"""

import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import msbt  # noqa: E402
import pak  # noqa: E402
import rtext  # noqa: E402

GC = os.path.join(HERE, "..", "..", "MP russian", "text")
MANUAL = os.path.join(HERE, "..", "text", "ru-remastered.json")
LABEL = re.compile(r"\[([0-9A-F]{8})\]_(\d+)$")
RM_CODE = re.compile(r"&rm=([0-9a-f]+);")


def word_set(ru):
    words = collections.Counter()
    for table in ru.values():
        for e in table.values():
            for w in re.findall(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*", rtext.GC_TAG.sub("", e["ru"]).replace("-\n", "-")):
                words[w.lower()] += 1
    return words


def unbreak(t, words):
    """Переносы перевода под ширину GameCube → строка без них; None — не решилось."""
    def fix(m):
        a, b = m.group(1), m.group(2)
        joined, hyph = (a + b).lower(), f"{a}-{b}".lower()
        if words[hyph] > words[joined]:
            return f"{a}-{b}"
        if words[joined]:
            return a + b
        raise LookupError(f"{a}-{b}")
    try:
        t = re.sub(r"([А-Яа-яЁё]+)-\n([А-Яа-яЁё]+)", fix, t)
    except LookupError:
        return None
    return re.sub(r"(?<!\n)\n(?!\n)", " ", t)


MARK = re.compile(r"‹(\d+)›")


def marked(en_rm):
    """Английский Remastered с кодами, заменёнными на ‹1›, ‹2›… по порядку."""
    n = 0
    out = []
    for k, t in rtext.rm_tokens(en_rm):
        if k == "code":
            n += 1
            out.append(f"‹{n}›")
        else:
            out.append(t)
    return "".join(out)


def decode_manual(s, en_rm):
    """Ручной перевод: ‹n› — n-й код английской строки Remastered; «&rm=hex;» — код как есть."""
    codes = [c for k, c in rtext.rm_tokens(en_rm) if k == "code"]
    used = {int(i) for i in MARK.findall(s)}
    if used != set(range(1, len(codes) + 1)):
        raise ValueError(f"коды {sorted(used)}, а в английском их {len(codes)}: {s!r}")
    s = MARK.sub(lambda m: codes[int(m.group(1)) - 1], s)
    return RM_CODE.sub(lambda m: bytes.fromhex(m.group(1)).decode("utf-16-le"), s)


def plain_en(s, tokens):
    """Английский без разметки и без разницы в пробелах/переносах — для поиска по тексту."""
    return re.sub(r"\s+", " ", "".join(rtext.texts(tokens(s)))).strip().lower()


def text_index(ru, en):
    """{английский GameCube без разметки: (таблица, индекс)} — только однозначные и переведённые."""
    idx, dup = {}, set()
    for sid, table in ru.items():
        for i in table:
            key = plain_en(en[sid]["strings"][int(i)], rtext.gc_tokens)
            if not key:
                continue
            if key in idx and idx[key] != (sid, i):
                # одинаковый английский с разным русским — неоднозначно
                if ru[idx[key][0]][idx[key][1]]["ru"] != table[i]["ru"]:
                    dup.add(key)
            else:
                idx[key] = (sid, i)
    return {k: v for k, v in idx.items() if k not in dup}


def russian(label, en_rm, ru, en, words, manual, report, by_text):
    if label in manual:
        return decode_manual(manual[label], en_rm)
    m = LABEL.match(label)
    sid, idx = (m.group(1), str(int(m.group(2)))) if m else (None, None)
    if not m or sid not in ru or idx not in ru[sid]:
        # Remastered перенумеровал часть таблиц: тот же английский — тот же перевод
        hit = by_text.get(plain_en(en_rm, rtext.rm_tokens))
        if hit is None:
            if en_rm.strip():
                report.append((label, "новая строка Remastered" if not m else "нет в переводе GameCube", en_rm))
            return None
        sid, idx = hit
    t = ru[sid][idx]["ru"]
    e = en[sid]["strings"][int(idx)]
    if t.count("\n") > e.count("\n") or (en_rm.count("\n") == 0 and t.count("\n")):
        fixed = unbreak(t, words)
        if fixed is None:
            report.append((label, "перенос: дефис или слово?", t))
        else:
            t = fixed
    rt, tt = rtext.rm_tokens(en_rm), rtext.gc_tokens(t)
    runs = rtext.texts(tt)
    codes = [c for k, c in rt if k == "code"]
    if not codes:
        return "".join(runs)
    # 1) теги GameCube, которые видны (цвет, значок, возврат цвета), — на коды Remastered по порядку:
    #    сохраняет русский порядок слов («из кордита» — цветное слово в середине)
    shown = significant(tt)
    if len(shown) == len(codes) and all(kind == code_role(c) for (kind, _), c in zip(shown, codes)):
        at = {i for _, i in shown}
        it = iter(codes)
        return "".join(next(it) if i in at else (tok if k == "text" else "")
                       for i, (k, tok) in enumerate(tt))
    # 2) куски текста между кодами Remastered — русскими кусками по порядку
    if len(rtext.texts(rt)) == len(runs):
        it = iter(runs)
        return "".join(c if k == "code" else next(it) for k, c in rt)
    report.append((label, "коды Remastered не совпали с тегами GameCube", en_rm))
    return None


def code_role(code):
    """Роль кода Remastered: color (цвет и его сброс), icon (значок), other."""
    k = rtext.code_kind(code)
    if k == (0, 3):
        return "color"
    if k[0] == 1 or k[0] == "close":
        return "icon"
    return "other"


def significant(tokens):
    """[(роль, индекс токена)] видимых тегов GameCube: цвет, сброс цвета через &pop;, значок."""
    out, colored = [], 0
    for i, (k, tok) in enumerate(tokens):
        if k != "code":
            continue
        if tok.startswith("&main-color="):
            out.append(("color", i))
            colored += 1
        elif tok == "&pop;" and colored:
            out.append(("color", i))
            colored -= 1
        elif tok.startswith("&image="):
            out.append(("icon", i))
    return out


def load_rows(pak_dir):
    """{(файл, GUID MSBT): [(метка, английский)]} по всем MSBT."""
    rows = {}
    for p in sorted(glob.glob(os.path.join(pak_dir, "**", "*.pak"), recursive=True)):
        b = open(p, "rb").read()
        for t, g, v, off, us, cs in pak.resources(b):
            if t != "MSBT":
                continue
            res = b[off:off + cs]
            s, e = msbt.lang_blocks(res)["USEN"]
            rows[(os.path.relpath(p, pak_dir), g)] = msbt.parse(res[s:e])
    return rows


def transfer(pak_dir):
    ru = json.load(open(os.path.join(GC, "ru.json"), encoding="utf-8"))
    en = json.load(open(os.path.join(GC, "en.json"), encoding="utf-8"))
    manual = json.load(open(MANUAL, encoding="utf-8")) if os.path.exists(MANUAL) else {}
    words = word_set(ru)
    by_text = text_index(ru, en)
    out, report = {}, []
    for key, rows in load_rows(pak_dir).items():
        for label, en_rm in rows:
            if label in out:
                continue
            r = russian(label, en_rm, ru, en, words, manual, report, by_text)
            if r is not None:
                out[label] = r
    seen, uniq = set(), []
    for row in report:
        if row[0] not in seen:
            seen.add(row[0])
            uniq.append(row)
    return out, uniq


def worklist(pak_dir, path):
    """TSV для ручного перевода: метка, причина, английский с ‹n›, подсказка из перевода GameCube."""
    import difflib
    ru = json.load(open(os.path.join(GC, "ru.json"), encoding="utf-8"))
    en = json.load(open(os.path.join(GC, "en.json"), encoding="utf-8"))
    gc = {}
    for sid, table in ru.items():
        for i in table:
            gc.setdefault(plain_en(en[sid]["strings"][int(i)], rtext.gc_tokens), table[i]["ru"])
    keys = list(gc)
    out, report = transfer(pak_dir)
    english = {label: t for rows in load_rows(pak_dir).values() for label, t in rows}
    with open(path, "w", encoding="utf-8") as f:
        f.write("метка\tпричина\tанглийский\tподсказка (перевод GameCube)\n")
        for label, why, _ in report:
            e = english[label]
            q = plain_en(e, rtext.rm_tokens)
            near = difflib.get_close_matches(q, keys, n=1, cutoff=0.75) if len(q) > 3 else []
            hint = gc[near[0]] if near else ""
            f.write(f"{label}\t{why}\t{marked(e)!r}\t{hint!r}\n")


if __name__ == "__main__":
    if sys.argv[1] == "worklist":
        worklist(sys.argv[2], sys.argv[3])
        sys.exit(0)
    out, report = transfer(sys.argv[1])
    print(f"переведено строк: {len(out)}; в отчёте: {len(report)}")
    for k, n in collections.Counter(r[1] for r in report).most_common():
        print(f"  {k}: {n}")
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            for label, why, text in report:
                f.write(f"{label}\t{why}\t{text!r}\n")
