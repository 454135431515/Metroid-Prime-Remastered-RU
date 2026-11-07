#!/bin/sh
# Все проверки проекта. Падает на первой ошибке.
set -e
cd "$(dirname "$0")/.."

# Данные Nintendo и секреты консоли не должны попасть в индекс.
if git diff --cached --name-only | grep -E -i '\.(nsp|nsz|xci|xcz|nca|keys|tik|pak|arc|msbt|font|txtr)$|^(work|mod|build|dist)/'; then
  echo "test.sh: в индексе данные игры или ключи (см. выше)" >&2
  exit 1
fi

python -I tools/test_formats.py
