"""Сборка библиотеки: структура папок, OBJ/MTL, текстуры, спецификация, индекс."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .geometry import Part
from .materials import MATERIALS, write_textures
from .modules import MODULES, ModuleSpec, build_module
from .obj_export import write_mtl, write_obj
from .preview import render_jpg, write_preview

LIBRARY_NAME = "PRO100_Библиотека_Модули"


def _spec_rows(spec: ModuleSpec, parts: list[Part]) -> list[dict]:
    rows = []
    for i, part in enumerate(parts, start=1):
        dx, dy, dz = part.size
        # плита: две наибольшие стороны = длина/ширина, минимальная = толщина
        sides = sorted([dx, dy, dz], reverse=True)
        length, width, thickness = sides[0], sides[1], sides[2]
        rows.append(
            {
                "№": i,
                "Модуль": spec.title,
                "Деталь": part.name,
                "Материал": MATERIALS[part.material].title if part.material in MATERIALS else part.material,
                "Длина, мм": round(length, 1),
                "Ширина, мм": round(width, 1),
                "Толщина, мм": round(thickness, 1),
                "Кол-во": 1,
                "Кромка": part.edge,
                "Примечание": part.note,
            }
        )
    return rows


def build_library(out_dir: Path) -> dict:
    """Собрать всю библиотеку в out_dir. Возвращает индекс (dict)."""
    lib_root = out_dir / LIBRARY_NAME
    index: dict = {
        "library": LIBRARY_NAME,
        "units": "mm",
        "up_axis": "Z",
        "import_path": "Файл → Импорт → 3D модель (PRO100 5.20+)",
        "modules": [],
    }
    all_rows: list[dict] = []
    used_materials: set[str] = set()

    for spec in MODULES:
        parts = build_module(spec)
        used_materials |= {p.material for p in parts}

        target_dir = lib_root / spec.category
        target_dir.mkdir(parents=True, exist_ok=True)

        mtl_name = f"{spec.key}.mtl"
        write_obj(target_dir / f"{spec.key}.obj", parts, mtl_name, spec.title)
        write_mtl(target_dir / mtl_name, {p.material for p in parts})

        preview = write_preview(target_dir / f"{spec.key}.svg", parts, spec.title)
        thumb = render_jpg(target_dir / f"{spec.key}.jpg", parts, spec.title)

        rows = _spec_rows(spec, parts)
        all_rows += rows
        # спецификация по модулю
        with (target_dir / f"{spec.key}.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

        index["modules"].append(
            {
                "key": spec.key,
                "title": spec.title,
                "category": spec.category,
                "obj": str((target_dir / f"{spec.key}.obj").relative_to(out_dir)),
                "sizes_mm": {"W": spec.width, "H": spec.height, "D": spec.depth},
                "parts": len(parts),
                "preview": str(preview.relative_to(out_dir)),
                "thumbnail": str(thumb.relative_to(out_dir)) if thumb else None,
                "tags": spec.tags,
            }
        )

    written_textures = write_textures(lib_root / "Текстуры", used_materials)
    index["textures"] = [p.name for p in written_textures.values()]

    # общая спецификация по всей библиотеке
    if all_rows:
        with (out_dir / "Спецификация_всех_модулей.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(all_rows[0].keys()), delimiter=";")
            writer.writeheader()
            writer.writerows(all_rows)

    (out_dir / "library.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    (lib_root / "КАК_ИМПОРТИРОВАТЬ.txt").write_text(_import_instructions(index), encoding="utf-8")
    return index


def _import_instructions(index: dict) -> str:
    return f"""Библиотека: {index['library']}
Единицы: миллиметры, ось Z — вверх.

Импорт в PRO100 5.20 / 6 / 7:
1. Файл → Импорт → 3D модель.
2. Выберите .obj из нужной папки (например, «Кухня/Нижние/base_600.obj»).
3. В окне импорта:
   - «ед. изм.» = миллиметры;
   - ориентация полигонов = CW или CCW (не «двусторонняя»);
   - «копировать инфо о текстуре» → папка «Текстуры» этой библиотеки;
   - папка назначения = соответствующая папка библиотеки PRO100.
4. После импорта нажмите ПКМ по папке библиотеки → «Обновить»,
   чтобы появились миниатюры.

Итого модулей: {len(index['modules'])}.
Спецификация деталей: «Спецификация_всех_модулей.csv» в корне вывода.
"""
