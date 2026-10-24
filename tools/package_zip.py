#!/usr/bin/env python3
"""Упаковать собранную библиотеку в один ZIP для скачивания/передачи.

Использование: python3 tools/package_zip.py
Результат: PRO100_Библиотека_Модули.zip в корне репозитория.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, default=Path("library"))
    parser.add_argument("--out", type=Path, default=Path("PRO100_Библиотека_Модули.zip"))
    args = parser.parse_args()

    if not args.src.exists():
        print(f"Нет папки {args.src}. Сначала: python3 -m pro100lib build")
        return 1

    count = 0
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(args.src.rglob("*")):
            if path.is_file() and "_tmp" not in path.parts:
                zf.write(path, path.relative_to(args.src))
                count += 1

    size_mb = args.out.stat().st_size / 1024 / 1024
    print(f"Готово: {args.out} ({count} файлов, {size_mb:.1f} МБ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
