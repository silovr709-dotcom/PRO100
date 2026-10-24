"""Сборка библиотеки PRO100 по техничке и прайсу ВИСМА.

На вход — `data/visma-modules.json` (разобранные позиции прайса) и
`data/visma-2026-prices.json` (цены каркасов и фурнитуры).
На выход — дерево папок по подкатегориям прайса, OBJ/MTL/JPG/CSV на каждый
модуль, общий прайс-спецификация и индекс.

Цены только из прайса: цена каркаса берётся по артикулу, фурнитура — по
базовым позициям технички (петли Boyard, опоры h100, НПВ 450, навесы,
ручка 96). Фасад считается справочно: площадь × цена кв.м по категории плёнки.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .materials import MATERIALS
from .obj_export import _safe, write_mtl, write_obj
from .preview import render_jpg
from .visma import build_visma_parts, module_stats

LIBRARY_NAME = "PRO100_Библиотека_ВИСМА"

# базовые позиции фурнитуры по техничке (п.1, п.13): точное имя в прайсе
FX = {
    "hinge": "Петля Боярд 90°",
    "leg": "Опора регулируемая пвх h100мм",
    "runner": "НПВ Боярд DB4504Zn, (L 300, 350, 400, 450 )",
    "hanger": "Навесы регулируемые",
    "handle": "Ручка скоба Бабочка 96 хром",
}
HINGES_PER_DOOR = 2
LEGS_PER_UNIT = 4


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _price_index(prices: dict) -> dict[str, dict]:
    return {item["name"]: item for item in prices["items"]}


def _price_of(index: dict, name: str) -> dict | None:
    item = index.get(name)
    if item:
        return {"name": name, "price": item.get("price"), "unit": item.get("unit")}
    return None


def facade_prices(prices: dict) -> dict[int, float]:
    """Цена кв.м фасада МДФ в плёнке ПВХ 16 мм по категориям (из прайса).

    Имена позиций в прайсе совпадают для всех категорий, поэтому идём по
    исходному списку `items`, а не по индексу имён.
    """
    out: dict[int, float] = {}
    for item in prices["items"]:
        attrs = item.get("attrs") or {}
        name = item.get("name", "")
        if item["category"] != "Фасады: МДФ (ПВХ плёнка)":
            continue
        if attrs.get("толщина") != "16мм" or "Квадратный метр" not in name:
            continue
        category = (attrs.get("категория") or "").split()[0]
        if category.isdigit() and item.get("price"):
            out[int(category)] = float(item["price"])
    return out


def _file_stem(module: dict) -> str:
    return (
        f"{str(module['article']).zfill(3)}_"
        f"{_safe(module['series'])[:48]}_"
        f"{int(module['width'])}x{int(module['height'])}x{int(module['depth'])}"
    )


def _row(module: dict, parts, stats: dict, fx: dict, facades: dict[int, float]) -> dict:
    doors = int(module["doors"])
    drawers = int(module["drawers"])
    hinges = doors * HINGES_PER_DOOR
    cost_hinge = (fx.get("hinge", {}).get("price") or 0) * hinges
    cost_leg = (fx.get("leg", {}).get("price") or 0) * LEGS_PER_UNIT if module["kind"] == "base" else 0
    cost_runner = (fx.get("runner", {}).get("price") or 0) * drawers
    cost_hanger = (fx.get("hanger", {}).get("price") or 0) if module["kind"] == "wall" else 0
    cost_handle = (fx.get("handle", {}).get("price") or 0) * (doors + drawers)
    carcass = float(module.get("price") or 0)
    total = carcass + cost_hinge + cost_leg + cost_runner + cost_hanger + cost_handle
    area = stats["facade_m2"]

    row = {
        "Артикул": module["article"],
        "Категория прайса": module["subcategory"],
        "Серия": module["series"],
        "Ш, мм": round(module["width"]),
        "В, мм": round(module["height"]),
        "Г, мм": round(module["depth"]),
        "Двери": doors,
        "Ящики": drawers,
        "Полки": module["shelves"],
        "Цена каркаса, ₽": carcass,
        "Петли, ₽": round(cost_hinge, 2),
        "Опоры, ₽": round(cost_leg, 2),
        "Направляющие, ₽": round(cost_runner, 2),
        "Навесы, ₽": round(cost_hanger, 2),
        "Ручки, ₽": round(cost_handle, 2),
        "Итого базовый комплект, ₽": round(total, 2),
        "Фасад, м²": area,
    }
    for cat in sorted(facades):
        row[f"Фасад ПВХ 16мм кат.{cat}, ₽"] = round(area * facades[cat], 2)
    row.update(
        {
            "Деталей в модели": stats["parts"],
            "ЛДСП/ХДФ, м²": stats["ldsp_m2"],
            "Кромка, п.м": stats["edge_m"],
            "Основание размеров": module["basis"],
            "Примечания": "; ".join(module.get("notes") or []),
        }
    )
    return row


def build_visma_library(
    out_dir: Path,
    modules_path: Path,
    prices_path: Path,
    *,
    limit: int | None = None,
) -> dict:
    data = _load(modules_path)
    prices = _load(prices_path)
    index = _price_index(prices)
    facades = facade_prices(prices)
    fx = {key: _price_of(index, name) or {} for key, name in FX.items()}

    lib_root = out_dir / LIBRARY_NAME
    rows: list[dict] = []
    library: list[dict] = []
    modules = data["modules"][:limit] if limit else data["modules"]

    for module in modules:
        parts = build_visma_parts(module)
        stats = module_stats(parts)
        stem = _file_stem(module)
        folder = lib_root / module["subcategory"]
        folder.mkdir(parents=True, exist_ok=True)

        mtl_name = f"{stem}.mtl"
        obj_path = write_obj(folder / f"{stem}.obj", parts, mtl_name, module["series"])
        write_mtl(folder / mtl_name, {p.material for p in parts})
        # непрозрачные фасады: элемент читается как закрытый шкаф;
        # для модулей без дверей (стеллажи, полки) фасадов нет — видно наполнение
        thumb = render_jpg(folder / f"{stem}.png", parts, module["series"], size=448, facade_alpha=252)

        row = _row(module, parts, stats, fx, facades)
        row["Файл модели"] = str(obj_path.relative_to(out_dir))
        rows.append(row)

        with (folder / f"{stem}.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(row.keys()), delimiter=";")
            writer.writeheader()
            writer.writerow(row)

        library.append(
            {
                "article": module["article"],
                "series": module["series"],
                "subcategory": module["subcategory"],
                "kind": module["kind"],
                "sizes_mm": {
                    "W": round(module["width"]),
                    "H": round(module["height"]),
                    "D": round(module["depth"]),
                },
                "doors": module["doors"],
                "drawers": module["drawers"],
                "obj": str(obj_path.relative_to(out_dir)),
                "thumbnail": str(thumb.relative_to(out_dir)) if thumb else None,
                "price_carcass_rub": module.get("price"),
            }
        )

    _write_master_csv(out_dir / "Прайс-спецификация_ВИСМА.csv", rows)
    _write_price_reference(out_dir / "Справочник_цен_фурнитуры.csv", fx, facades)
    _write_excluded(out_dir / "Не_вошло_в_библиотеку.csv", data.get("excluded", []))

    summary = {
        "library": LIBRARY_NAME,
        "source": data["source"],
        "units": "mm",
        "up_axis": "Z",
        "module_count": len(library),
        "excluded": len(data.get("excluded", [])),
        "facade_price_per_m2": facades,
        "fittings": {k: v.get("price") for k, v in fx.items()},
        "items": library,
    }
    (out_dir / "library.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (lib_root / "КАК_ИМПОРТИРОВАТЬ.txt").write_text(_instructions(summary), encoding="utf-8")
    return summary


def _write_master_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def _write_price_reference(path: Path, fx: dict, facades: dict[int, float]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(["Позиция", "Наименование в прайсе", "Цена, ₽", "Ед.", "Источник"])
        for key, item in fx.items():
            writer.writerow([key, item.get("name", "—"), item.get("price", "—"),
                             item.get("unit", ""), "ВИСМА 2026 КХМ, «Доп комплект»/«Ручки»"])
        for cat, price in sorted(facades.items()):
            writer.writerow([f"фасад ПВХ кат.{cat}", "Квадратный метр фасада, 16 мм",
                             price, "кв.м", "лист «МДФ(ПВХ)»"])


def _write_excluded(path: Path, excluded: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(["Артикул", "Серия", "Ширина, мм", "Цена, ₽", "Причина"])
        for item in excluded:
            writer.writerow([item.get("article"), item.get("series"), item.get("width"),
                             item.get("price"), item.get("excluded_reason")])


def _instructions(summary: dict) -> str:
    return f"""Библиотека: {summary['library']}
Источники: {summary['source']['pricebook']} (цены, артикулы) + {summary['source']['tech']} (конструкция)
Модулей: {summary['module_count']}   Не вошло (непрямоугольные формы): {summary['excluded']}
Единицы: миллиметры, ось Z — вверх, фасад смотрит в −Y.

Импорт в PRO100 5.20 / 6 / 7:
1. Файл → Импорт → 3D модель.
2. Выберите .obj нужного модуля из папки подкатегории (файл начинается с артикула прайса).
3. В окне импорта: «ед. изм.» = мм, ориентация полигонов = CW или CCW,
   папка назначения — соответствующая папка библиотеки PRO100.
4. ПКМ по папке библиотеки → «Обновить» (появятся миниатюры).
5. В свойствах элемента задайте название по серии и артикулу из
   «Прайс-спецификация_ВИСМА.csv».

Что учтено по техничке:
- ЛДСП 16 мм, кромка ПВХ 0,4 мм, задняя стенка ХДФ 3 мм в паз на 16 мм от заднего края;
- зазор фасадов 4 мм; фасады накладные, МДФ 16 мм;
- столы: каркас 720 мм, глубина 500, опоры 100, цоколь ЛДСП 95 мм с заглублением 18 мм;
- навесные: глубина 300 (внутренняя 284); пеналы: 560;
- ящики НПВ: глубина 450, корпус по таблице технички (100/190/280 мм).

Чего в модели НЕТ (считать отдельно по прайсу):
- столешницы, стеновые панели, бортики, козырёк, багеты, пилястры;
- фрезеровки фасадов и их категория (цена фасада в спецификации — справочная, по площади);
- петли/направляющие сверх базовых, газлифты, подсветка, профиль GOLA.
"""
