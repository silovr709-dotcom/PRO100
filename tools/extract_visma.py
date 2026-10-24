#!/usr/bin/env python3
"""ETL: прайс ВИСМА 2026 (подмножество JSON) + техничка → каталог модулей для PRO100.

Источник цен: `data/visma-2026-prices.json` (выгрузка из репозитория Calculator,
лист «каркас шк» / «каркас ст» прайса «ВИСМА 2026 КХМ.xlsm»).
Источник размеров и правил: `data/visma-tech.json` (Техничка 1.08.2025.pdf).

Результат: `data/visma-modules.json` — по каждой позиции прайса разобранные
габариты, комплектация и основание, откуда взяты размеры.

Использование: python3 tools/extract_visma.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRICES = ROOT / "data" / "visma-2026-prices.json"
TECH = ROOT / "data" / "visma-tech.json"
OUT = ROOT / "data" / "visma-modules.json"

EXCLUDE_PATTERNS = (
    "угловой",
    "угловая",
    "скос",
    "радиус",
    "трапеци",
    "гармошк",
    "вогнут",
)

WORDS = {
    "1-но дверный": 1,
    "1-но дверная": 1,
    "2-х дверный": 2,
    "2-х дверная": 2,
    "2мя дверками": 2,
    "2мя дверями": 2,
    "4мя дверками": 4,
    "3мя дверками": 3,
}


def parse_size(raw: str) -> dict:
    """'600мм (В)' / '600х308х300' / '600*400*300 16мм' → габариты."""
    text = (raw or "").lower().replace("*", "х").replace(" ", "")
    triple = re.match(r"(\d+(?:[.,]\d+)?)х(\d+(?:[.,]\d+)?)х(\d+(?:[.,]\d+)?)", text)
    if triple:
        w, a, b = (float(g.replace(",", ".")) for g in triple.groups())
        return {"width": w, "dims": (w, a, b)}
    single = re.match(r"(\d+(?:[.,]\d+)?)", text)
    if single:
        return {"width": float(single.group(1).replace(",", ".")), "dims": None}
    return {"width": 0.0, "dims": None}


def parse_height(series: str) -> float | None:
    match = re.search(r"н\s*=\s*(\d+)", series.lower())
    return float(match.group(1)) if match else None


def parse_doors(series: str) -> int:
    low = series.lower()
    if "с открытыми полками" in low or "полка открытая" in low or "виница" in low:
        return 0
    for word, count in WORDS.items():
        if word in low:
            return count
    if "с 2мя ящиками,2мя дверками" in low:
        return 2
    if "4мя дверками" in low:
        return 4
    return 1


def parse_drawers(series: str) -> tuple[int, list[float]]:
    low = series.lower()
    heights = [float(x) for x in re.findall(r"\d+", re.search(r"\((\d+(?:\+\d+)+)\)", low).group(1))] \
        if re.search(r"\((\d+(?:\+\d+)+)\)", low) else []
    total = 0
    for m in re.finditer(r"с\s*(\d+)\s*-?\s*мя\s*ящик", low):
        total += int(m.group(1))
    if "с ящиком" in low and total == 0:
        total = 1
    if "ящиками" in low and total == 0:
        total = 2
    if total and not heights:
        heights = [180.0] * total
    if heights and not total:
        total = len(heights)
    if total and len(heights) == total:
        # 180/270/360 — номинальные высоты; 176/266/356 — реальные фасады по техничке
        heights = [h - 4 for h in heights]
    return total, heights


def parse_shelves(series: str, kind: str, height: float) -> int:
    low = series.lower()
    if "без полки" in low:
        return 0
    if "1 полка" in low:
        return 1
    if "с полками" in low:
        return 4 if kind == "tall" else 1
    if "с открытыми полками" in low or "полка открытая" in low:
        return max(1, int(height // 200) - 1)
    if kind == "tall":
        return 4
    return 0 if "под врезную мойку" in low or "под ДШ" in low else 1


def classify(series: str) -> str:
    low = series.lower()
    if "виница" in low:
        return "wine"
    if "пенал" in low:
        return "tall"
    if "стол" in low:
        return "base"
    return "wall"


def build_entry(item: dict, tech: dict) -> dict:
    series = (item.get("attrs") or {}).get("серия") or item["name"]
    size = (item.get("attrs") or {}).get("размер") or ""
    parsed = parse_size(size)
    kind = classify(series)
    excluded = next((p for p in EXCLUDE_PATTERNS if p in series.lower()), None)

    width = parsed["width"]
    if parsed["dims"]:
        _, height, depth = parsed["dims"]
    else:
        depth = {
            "wall": tech["wall_units"]["depth"],
            "base": tech["base_units"]["depth"],
            "tall": tech["tall_units"]["depth"],
            "wine": tech["wall_units"]["depth"],
        }[kind]
        height = parse_height(series)
        if height is None:
            height = {"wall": 720.0, "base": 720.0, "tall": 2000.0, "wine": 308.0}[kind]

    total_drawers, drawer_heights = parse_drawers(series)
    doors = parse_doors(series)
    shelves = parse_shelves(series, kind, height)

    notes: list[str] = []
    if "мойку" in series.lower():
        notes.append("под мойку: задняя стенка набивная, без полки (техничка, п.4)")
    if "под дш" in series.lower() or "духов" in series.lower():
        notes.append("проём под духовой шкаф/технику — проверить по бланку заказа")
    if "нишей" in series.lower():
        notes.append("открытая ниша: принята высотой 200 мм")
    if "проходной" in series.lower():
        notes.append("проходной: отступ 100 мм от стены, стыковочные планки")
    if "буфет" in series.lower():
        notes.append("буфет: дверь + ящики, высота корпуса 1282/1462 мм")
    if height > 1000:
        notes.append("фасад выше 1000 мм — рекомендация «корректор фасада» (техничка, п.18)")

    if parsed["dims"]:
        basis = "габариты из прайса (Ш×В×Г)"
    elif parse_height(series) is not None:
        basis = "высота из названия серии, глубина по техничке"
    else:
        basis = "высота по умолчанию (720 стол / 720 навесной / 2000 пенал) — уточнить"

    return {
        "article": item.get("article"),
        "series": series,
        "name": item["name"],
        "price": item.get("price"),
        "unit": item.get("unit"),
        "subcategory": item.get("subcategory"),
        "category": item["category"],
        "kind": kind,
        "width": width,
        "height": height,
        "depth": depth,
        "doors": doors,
        "drawers": total_drawers,
        "drawer_facade_heights": drawer_heights,
        "shelves": shelves,
        "niche_h": 200.0 if "нишей" in series.lower() else 0.0,
        "legs": tech["base_units"]["legs"][0] if kind == "base" else 0.0,
        "plinth": tech["base_units"]["plinth_ldsp_heights"][0] if kind == "base" else 0.0,
        "back_panel": "набивная (ЛДСП)" if kind == "wine" else "ХДФ в паз",
        "notes": notes,
        "basis": basis,
        "excluded": excluded,
        "excluded_reason": (
            f"позиция «{excluded}»: форма корпуса не прямоугольная — "
            "геометрию задавать в редакторе формы PRO100"
        ) if excluded else None,
    }


def main() -> int:
    prices = json.loads(PRICES.read_text(encoding="utf-8"))
    tech = json.loads(TECH.read_text(encoding="utf-8"))

    corpus = [i for i in prices["items"] if i["category"].startswith("Корпуса")]
    entries = [build_entry(i, tech) for i in corpus]

    usable = [e for e in entries if not e["excluded"]]
    excluded = [e for e in entries if e["excluded"]]
    unknown_width = [e for e in usable if not e["width"]]

    payload = {
        "source": {
            "pricebook": prices["meta"]["sourceFile"],
            "pricebookSubset": str(PRICES.relative_to(ROOT)),
            "tech": tech["source"],
            "generatedBy": "tools/extract_visma.py",
        },
        "stats": {
            "positions": len(entries),
            "library": len(usable),
            "excluded": len(excluded),
            "no_width": len(unknown_width),
        },
        "modules": usable,
        "excluded": excluded,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2))
    print(f"→ {OUT.relative_to(ROOT)}")
    if unknown_width:
        print("Без ширины:", [e["series"] for e in unknown_width][:5], file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
