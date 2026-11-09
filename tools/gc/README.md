# Копия кода шрифтов перевода GameCube

`cyrillic.py`, `hd_font.py`, `font.py` и нарисованные буквы `glyphs/*.svg` (ADR 0004 metroid-prime-ru) — байт в байт из
[metroid-prime-ru](https://github.com/454135431515/metroid-prime-ru) `tools/` (MIT), чтобы сборка
работала из одного этого репозитория (ADR 0004). Здесь не править: изменения вносятся в
metroid-prime-ru, затем `python -I tools/sync_gc.py`; `tools/test.sh` проверяет совпадение.
