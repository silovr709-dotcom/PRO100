#!/usr/bin/env python3
"""Собрать общий каталог-превью библиотеки: сетка миниатюр всех модулей.

Использование: python3 tools/make_catalog_preview.py --out library_out/Каталог_модулей.jpg
Требует Pillow (для JPG). Без Pillow печатает предупреждение.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pro100lib.modules import MODULES, build_module  # noqa: E402
from pro100lib.preview import render_jpg  # noqa: E402


FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _load_font(size: int):
    """Шрифт с кириллицей; если не нашли — стандартный (латиница)."""
    from PIL import ImageFont

    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("library_out/Каталог_модулей.jpg"))
    parser.add_argument("--cell", type=int, default=320)
    args = parser.parse_args()

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Нужен Pillow: pip install pillow", file=sys.stderr)
        return 1

    font = _load_font(16)
    small = _load_font(13)

    cell = args.cell
    cols = 4
    rows = (len(MODULES) + cols - 1) // cols
    label_h = 62
    sheet = Image.new("RGB", (cols * cell, rows * (cell + label_h) + 60), (250, 250, 248))
    draw = ImageDraw.Draw(sheet)
    draw.text((20, 18), f"Библиотека модулей PRO100 — {len(MODULES)} элементов", fill=(20, 20, 20), font=font)

    for i, spec in enumerate(MODULES):
        parts = build_module(spec)
        tmp = args.out.parent / "_tmp" / f"{spec.key}.jpg"
        path = render_jpg(tmp, parts, spec.title, size=cell - 16)
        if path is None:
            print("Не удалось отрисовать миниатюру", file=sys.stderr)
            return 1
        thumb = Image.open(path).convert("RGB")
        col, row = i % cols, i // cols
        x = col * cell + 8
        y = 60 + row * (cell + label_h)
        sheet.paste(thumb, (x, y))
        draw.text((x, y + cell - 6), spec.key, fill=(40, 40, 40), font=small)
        w = int(spec.width)
        h = int(spec.height)
        d = int(spec.depth)
        draw.text((x, y + cell + 10), f"{w}x{h}x{d} мм", fill=(90, 90, 90), font=small)
        draw.text((x, y + cell + 26), _fit(spec.title, 34), fill=(70, 70, 70), font=small)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out, quality=88)
    print(f"Готово: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
