"""Параметрические корпусные модули (кухня/шкафы/стеллажи).

Каждый модуль описывается габаритами и собирается из плит: боковины, дно,
крыша, полки, задняя стенка ХДФ, фасады, цоколь. Все размеры в мм.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .geometry import Part, box

T = 16.0          # толщина ЛДСП
BACK = 3.0        # ХДФ задняя стенка
FACADE_T = 18.0   # МДФ фасад
GAP = 2.0         # зазор между фасадами, на сторону


@dataclass
class ModuleSpec:
    key: str                 # латинский ключ (имя файла)
    title: str               # название для библиотеки
    category: str            # папка в библиотеке PRO100
    width: float
    height: float
    depth: float
    kind: str                # base | drawers | wall | tall | shelving
    shelves: int = 1
    doors: int = 1
    drawers: int = 0
    plinth: float = 100.0
    countertop: bool = False   # включить столешницу в модель (обычно она отдельным элементом)
    material_body: str = "ldsp_white"
    material_facade: str = "mdf_facade"
    tags: list[str] = field(default_factory=list)


MODULES: list[ModuleSpec] = [
    ModuleSpec("base_400", "Тумба нижняя 400", "Кухня/Нижние", 400, 720, 500, "base", shelves=1, doors=1),
    ModuleSpec("base_600", "Тумба нижняя 600", "Кухня/Нижние", 600, 720, 500, "base", shelves=1, doors=1),
    ModuleSpec("base_800_double", "Тумба нижняя 800 (2 фасада)", "Кухня/Нижние", 800, 720, 500, "base", shelves=1, doors=2),
    ModuleSpec("sink_600", "Тумба под мойку 600", "Кухня/Нижние", 600, 720, 500, "base", shelves=0, doors=1, tags=["мойка"]),
    ModuleSpec("drawers_600", "Тумба с ящиками 600 (3 ящика)", "Кухня/Нижние", 600, 720, 500, "drawers", shelves=0, doors=0, drawers=3),
    ModuleSpec("wall_400", "Шкаф навесной 400", "Кухня/Верхние", 400, 720, 300, "wall", shelves=1, doors=1),
    ModuleSpec("wall_600_double", "Шкаф навесной 600 (2 фасада)", "Кухня/Верхние", 600, 720, 300, "wall", shelves=1, doors=2),
    ModuleSpec("tall_400", "Пенал 400", "Шкафы/Пеналы", 400, 2100, 600, "tall", shelves=4, doors=1, plinth=100),
    ModuleSpec("tall_800_double", "Шкаф-купе 800 (2 фасада)", "Шкафы/Пеналы", 800, 2200, 600, "tall", shelves=4, doors=2, plinth=100),
    ModuleSpec("shelving_600", "Стеллаж открытый 600", "Шкафы/Стеллажи", 600, 1800, 400, "shelving", shelves=4, doors=0, plinth=0),
]


def _body(spec: ModuleSpec, *, bottom_offset: float) -> list[Part]:
    """Корпус: боковины, дно, крыша. Глубина — по spec.depth."""
    w, h, d = spec.width, spec.height, spec.depth
    body_top = h
    z0 = bottom_offset
    parts: list[Part] = [
        box("боковина левая", 0, 0, z0, T, d, body_top - z0, spec.material_body,
            edge="1,0 мм по фасаду"),
        box("боковина правая", w - T, 0, z0, T, d, body_top - z0, spec.material_body,
            edge="1,0 мм по фасаду"),
        box("дно", T, 0, z0, w - 2 * T, d - BACK, T, spec.material_body,
            note="соединение на конфирмат/эксцентрик"),
        box("крыша", T, 0, body_top - T, w - 2 * T, d - BACK, T, spec.material_body),
        box("задняя стенка", T, d - BACK, z0, w - 2 * T, BACK, body_top - z0, "hdf_back"),
    ]
    return parts


def _shelves(spec: ModuleSpec, *, z_start: float, z_end: float, count: int) -> list[Part]:
    if count <= 0:
        return []
    parts: list[Part] = []
    inner_h = z_end - z_start
    step = inner_h / (count + 1)
    for i in range(count):
        z = z_start + step * (i + 1) - T / 2
        parts.append(
            box(f"полка {i + 1}", T, 0, z, spec.width - 2 * T, spec.depth - BACK - 20, T,
                spec.material_body, edge="по фасаду 1,0 мм")
        )
    return parts


def _facades(spec: ModuleSpec, *, z0: float, z1: float, doors: int) -> list[Part]:
    """Фасады накладные, с зазорами по 2 мм."""
    if doors <= 0:
        return []
    parts: list[Part] = []
    zone_w = (spec.width - GAP * (doors + 1)) / doors
    for i in range(doors):
        x = GAP + i * (zone_w + GAP)
        parts.append(
            box(f"фасад {i + 1}", x, -FACADE_T, z0 + GAP, zone_w, FACADE_T, (z1 - z0) - 2 * GAP,
                spec.material_facade, edge="2,0 мм по периметру", note="накладной, петли 110°")
        )
    return parts


def _drawer_fronts(spec: ModuleSpec, *, z0: float, z1: float, count: int) -> tuple[list[Part], list[Part]]:
    """Ящики: фасады + корпуса ящиков (упрощённо, 4 царги)."""
    if count <= 0:
        return [], []
    fronts: list[Part] = []
    boxes: list[Part] = []
    height = (z1 - z0 - GAP * (count + 1)) / count
    for i in range(count):
        z = z0 + GAP + i * (height + GAP)
        fronts.append(
            box(f"фасад ящика {i + 1}", GAP, -FACADE_T, z, spec.width - 2 * GAP, FACADE_T, height,
                spec.material_facade, edge="2,0 мм по периметру", note="направляющие скрытые")
        )
        box_w = spec.width - 2 * T - 26
        box_d = spec.depth - 60
        boxes.append(box(f"дно ящика {i + 1}", T + 13, 0, z + 10, box_w, box_d, T, spec.material_body))
        boxes.append(box(f"царга передняя {i + 1}", T + 13, 0, z + 10, box_w, T, 90, spec.material_body))
        boxes.append(box(f"царга задняя {i + 1}", T + 13, box_d - T, z + 10, box_w, T, 90, spec.material_body))
        boxes.append(box(f"царга левая {i + 1}", T + 13, 0, z + 10, T, box_d, 90, spec.material_body))
        boxes.append(box(f"царга правая {i + 1}", T + 13 + box_w - T, 0, z + 10, T, box_d, 90, spec.material_body))
    return fronts, boxes


def build_module(spec: ModuleSpec) -> list[Part]:
    """Собрать геометрию модуля."""
    parts: list[Part] = []

    if spec.kind == "shelving":
        # открытый стеллаж: боковины, крыша, дно, полки
        parts += _body(spec, bottom_offset=0.0)
        parts += _shelves(spec, z_start=0.0, z_end=spec.height, count=spec.shelves)
        return parts

    if spec.kind == "wall":
        parts += _body(spec, bottom_offset=0.0)
        parts += _shelves(spec, z_start=0.0, z_end=spec.height, count=spec.shelves)
        parts += _facades(spec, z0=0.0, z1=spec.height, doors=spec.doors)
        return parts

    # base / drawers / tall — с цоколем
    plinth = spec.plinth
    parts.append(box("цоколь", 0, 0, 0, spec.width, spec.depth - 40, plinth, "plinth",
                     note="регулируемые опоры 100 мм"))
    parts += _body(spec, bottom_offset=plinth)

    facade_z0, facade_z1 = 0.0, spec.height
    if spec.kind == "base" or spec.kind == "drawers":
        facade_z0, facade_z1 = plinth, spec.height

    inner_z0, inner_z1 = plinth + T, spec.height - T
    parts += _shelves(spec, z_start=inner_z0, z_end=inner_z1, count=spec.shelves)

    if spec.kind == "drawers":
        fronts, boxes_ = _drawer_fronts(spec, z0=facade_z0, z1=facade_z1, count=spec.drawers)
        parts += fronts + boxes_
    else:
        parts += _facades(spec, z0=facade_z0, z1=facade_z1, doors=spec.doors)

    if spec.countertop and spec.kind in {"base", "drawers"}:
        parts.append(box("столешница", 0, 0, spec.height, spec.width, spec.depth, 38,
                         "ldsp_white", note="38 мм, свес 0 мм"))
    return parts
