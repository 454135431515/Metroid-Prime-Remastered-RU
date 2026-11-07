"""Копии из перевода GameCube (metroid-prime-ru, соседняя папка `MP russian`), чтобы игроку
хватало одного этого репозитория (ADR 0004).

    python -I tools/sync_gc.py           # обновить tools/gc/ и text/ru-labels.json
    python -I tools/sync_gc.py --check   # только сверить (tools/test.sh)

- tools/gc/: код шрифтов (cyrillic.py, hd_font.py, font.py) — байт в байт как в metroid-prime-ru;
- text/ru-labels.json: {метка MSBT: русская строка} — итог tools/transfer.py по work/romfs. Только
  перевод и коды разметки, без английского текста: en.json GameCube — данные Nintendo.
Нет соседней папки или work/romfs — соответствующая сверка пропускается.
"""

import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
GC_TOOLS = os.path.join(HERE, "..", "..", "MP russian", "tools")
VENDOR = os.path.join(HERE, "gc")
FILES = ("cyrillic.py", "hd_font.py", "font.py")
LABELS = os.path.join(HERE, "..", "text", "ru-labels.json")
ROMFS = os.path.join(HERE, "..", "work", "romfs")


def labels_text():
    import transfer
    out, report = transfer.transfer(ROMFS)
    if report:
        raise SystemExit(f"без перевода {len(report)} строк: {[r[0] for r in report][:5]}")
    en = {label: text for rows in transfer.load_rows(ROMFS).values() for label, text in rows}
    out = {k: v for k, v in out.items() if v != en.get(k)}  # совпало с английским — не перевод
    return json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main(check=False):
    stale = []
    if os.path.isdir(GC_TOOLS):
        for name in FILES:
            src, dst = os.path.join(GC_TOOLS, name), os.path.join(VENDOR, name)
            same = os.path.exists(dst) and open(src, "rb").read() == open(dst, "rb").read()
            if not same:
                stale.append(f"tools/gc/{name}")
                if not check:
                    shutil.copyfile(src, dst)
    else:
        print("sync_gc: нет папки MP russian — копии кода не сверены")
    if os.path.isdir(ROMFS) and os.path.isdir(GC_TOOLS):
        text = labels_text()
        old = open(LABELS, encoding="utf-8").read() if os.path.exists(LABELS) else None
        if text != old:
            stale.append("text/ru-labels.json")
            if not check:
                open(LABELS, "w", encoding="utf-8").write(text)
    else:
        print("sync_gc: нет work/romfs — text/ru-labels.json не сверен")
    if check and stale:
        raise SystemExit(f"sync_gc: устарело {', '.join(stale)} — запустите tools/sync_gc.py")
    print(f"sync_gc: {'обновлено ' + ', '.join(stale) if stale and not check else 'ok'}")


if __name__ == "__main__":
    main("--check" in sys.argv[1:])
