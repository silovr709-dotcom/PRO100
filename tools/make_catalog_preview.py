#!/usr/bin/env python3
"""Каталог-превью библиотеки: сетка миниатюр всех модулей в один JPG.

Два режима:
  python3 tools/make_catalog_preview.py                      # встроенные модули pro100lib
  python3 tools/make_catalog_preview.py --library library_visma --out library_visma/Каталог.jpg

В режиме --library берутся миниатюры и подписи из `library.json`
(его пишут и `pro100lib build`, и сборка библиотеки ВИСМА).
Требует Pillow.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _load_font(size: int):
    from PIL import ImageFont

    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _entries_from_library(lib: Path) -> tuple[str, list[dict]]:
    data = json.loads((lib / "library.json").read_text(encoding="utf-8"))
    entries = []
    raw = data.get("items")
    if not isinstance(raw, list):
        raw = data.get("modules")
    if not isinstance(raw, list):
        raw = []
    for item in raw:
        thumb = item.get("thumbnail")
        if not thumb:
            continue
        sizes = item.get("sizes_mm") or {}
        w = sizes.get("W") or sizes.get("w")
        h = sizes.get("H") or sizes.get("h")
        d = sizes.get("D") or sizes.get("d")
        title = item.get("series") or item.get("title") or ""
        label = item.get("article")
        entries.append(
            {
                "thumb": lib / thumb,
                "code": str(label) if label is not None else str(item.get("key", "")),
                "title": title,
                "group": item.get("subcategory") or item.get("category") or "",
                "sizes": f"{w}x{h}x{d}",
            }
        )
    name = data.get("library", lib.name)
    return name, entries


def _entries_from_modules() -> tuple[str, list[dict]]:
    from pro100lib.modules import MODULES, build_module
    from pro100lib.preview import render_jpg

    entries = []
    tmp_dir = Path("_tmp")
    for spec in MODULES:
        parts = build_module(spec)
        path = render_jpg(tmp_dir / f"{spec.key}.jpg", parts, spec.title, size=304)
        if path is None:
            return "", []
        entries.append(
            {
                "thumb": path,
                "code": spec.key,
                "title": spec.title,
                "group": spec.category,
                "sizes": f"{int(spec.width)}x{int(spec.height)}x{int(spec.depth)}",
            }
        )
    return "Библиотека модулей PRO100", entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, default=None, help="папка с library.json")
    parser.add_argument("--out", type=Path, default=None, help="куда сохранить JPG")
    parser.add_argument("--cell", type=int, default=320)
    parser.add_argument("--cols", type=int, default=4)
    parser.add_argument("--group-by", default=None, help="subcategory|none — отдельный лист на группу")
    parser.add_argument("--out-dir", type=Path, default=None, help="папка для листов по группам")
    args = parser.parse_args()

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Нужен Pillow: pip install pillow", file=sys.stderr)
        return 1

    if args.library:
        title, entries = _entries_from_library(args.library)
        out = args.out or args.library / "Каталог.jpg"
    else:
        title, entries = _entries_from_modules()
        out = args.out or Path("library/Каталог_модулей.jpg")

    if not entries:
        print("Нечего рисовать: нет миниатюр в library.json", file=sys.stderr)
        return 1

    font = _load_font(15)
    small = _load_font(13)
    if args.group_by == "subcategory":
        groups: dict[str, list[dict]] = {}
        for entry in entries:
            groups.setdefault(entry["group"] or "Прочее", []).append(entry)
        out_dir = args.out_dir or out.parent / "Каталог"
        out_dir.mkdir(parents=True, exist_ok=True)
        for group, group_entries in groups.items():
            safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in group).strip()
            _render_sheet(f"{title} — {group}", group_entries, out_dir / f"{safe}.jpg", args.cell, args.cols)
        # обзорный лист: по одному представителю группы
        overview = [group_entries[0] for group_entries in groups.values()]
        _render_sheet(f"{title} — обзор категорий", overview, out, args.cell, args.cols)
        print(f"Листы по категориям: {out_dir} ({len(groups)} шт.), обзор: {out}")
        return 0

    _render_sheet(title, entries, out, args.cell, args.cols)
    return 0


def _render_sheet(title: str, entries: list[dict], out: Path, cell: int, cols: int) -> None:
    from PIL import Image, ImageDraw

    font = _load_font(15)
    small = _load_font(13)
    rows = (len(entries) + cols - 1) // cols
    label_h = 64
    sheet = Image.new("RGB", (cols * cell, rows * (cell + label_h) + 56), (250, 250, 248))
    draw = ImageDraw.Draw(sheet)
    draw.text((20, 18), f"{title} — {len(entries)} элементов", fill=(20, 20, 20), font=font)

    for i, entry in enumerate(entries):
        thumb = Image.open(entry["thumb"]).convert("RGB").resize((cell - 16, cell - 16))
        col, row = i % cols, i // cols
        x = col * cell + 8
        y = 56 + row * (cell + label_h)
        sheet.paste(thumb, (x, y))
        draw.text((x, y + cell - 6), f'{entry["code"]}  {entry["sizes"]} мм', fill=(40, 40, 40), font=small)
        draw.text((x, y + cell + 12), _fit(entry["title"], 36), fill=(70, 70, 70), font=small)
        draw.text((x, y + cell + 30), _fit(entry["group"], 40), fill=(120, 120, 120), font=small)

    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=88)
    print(f"Готово: {out} ({len(entries)} элементов)")


if __name__ == "__main__":
    raise SystemExit(main())
