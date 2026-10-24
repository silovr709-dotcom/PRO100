"""Геометрия модулей по техничке ВИСМА (Техничка 1.08.2025.pdf).

Правила, зашитые здесь (с указанием источника в техничке):

* каркас — ЛДСП 16 мм, кромка ПВХ 0.4 мм (п.4 «Каркас»);
* задняя стенка — ХДФ 3 мм в паз, паз смещён на 16 мм от заднего края,
  поэтому внутренняя глубина = глубина − 16 мм (п.4);
* в стол под мойку, под встраиваемый духовой шкаф и в бутылочницу задняя
  стенка набивная, полки нет (п.4);
* зазор между фасадами 4 мм (п.3);
* столы: каркас 720 мм, глубина 500 мм, опоры 100/150 мм, свес столешницы
  40 мм спереди и 60 мм сзади (п.2);
* навесные: глубина 300 мм, внутренняя 284 мм (п.2, п.4);
* пеналы: глубина 560 мм (по виницам 5–8 прайса и профилям пеналов);
* цоколь ЛДСП 95/145 мм, заглубление 18 мм от переда каркаса (п.8);
* ящики — НПВ, глубина 450 мм, дно ХДФ в паз (п.1, п.13);
  стандартные высоты фасадов ящиков для стола 720 мм: 176+536, 356+356,
  176+176+356, 176×4 (п.1);
* петли — 2 шт. на дверку (п.1), фасад выше 1000 мм — рекомендация
  «корректор фасада» (п.18).

Единицы — мм. Ось Z вверх, X вправо, Y вглубь (фасад смотрит в −Y).
"""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import Part, box

T = 16.0          # ЛДСП каркаса
BACK = 3.0        # ХДФ
GROOVE = 16.0     # паз от заднего края
GAP = 4.0         # зазор между фасадами
FACADE_T = 16.0   # МДФ в плёнке ПВХ
LEG = 100.0       # опоры столов
PLINTH_H = 95.0   # цоколь ЛДСП
PLINTH_SETBACK = 18.0

# техничка п.1: стандартные высоты корпусов ящиков (НПВ) под фасады 180/270/360
DRAWER_BODY_BY_FACADE = ((180.0, 100.0), (270.0, 190.0), (360.0, 280.0))
DRAWER_DEPTH = 450.0


def facade_stack(zone_h: float, weights: list[float], gap: float = GAP) -> list[float]:
    """Разложить фасады по высоте: зазоры сверху/снизу и между фасадами.

    Номинальные высоты из прайса/технички (176, 356, 180+180+360) сохраняют
    пропорции, но сумма подгоняется так, чтобы уложиться в зону с зазорами.
    """
    if not weights:
        return []
    gaps = gap * (len(weights) + 1)
    available = zone_h - gaps
    if available <= 0:
        return [max(1.0, zone_h / len(weights)) for _ in weights]
    total = sum(weights)
    return [available * w / total for w in weights]


def drawer_body_height(facade_h: float) -> float:
    for facade, body in DRAWER_BODY_BY_FACADE:
        if facade_h <= facade + 1:
            return body
    return DRAWER_BODY_BY_FACADE[-1][1]


def _carcass(
    width: float,
    height: float,
    depth: float,
    *,
    z0: float,
    shelf_count: int,
    shelf_inset: float,
    back: str,
    material: str,
    back_material: str,
) -> list[Part]:
    inner_w = width - 2 * T
    inner_d = depth - GROOVE
    parts = [
        box("боковина левая", 0, 0, z0, T, depth, height, material, edge="кромка ПВХ 0,4 мм по фасаду"),
        box("боковина правая", width - T, 0, z0, T, depth, height, material,
            edge="кромка ПВХ 0,4 мм по фасаду"),
        box("дно", T, 0, z0, inner_w, inner_d, T, material, note="евровинт/эксцентрик, 2 стяжки"),
        box("крыша", T, 0, z0 + height - T, inner_w, inner_d, T, material, note="евровинт/эксцентрик"),
    ]
    if back == "набивная":
        parts.append(box("задняя стенка набивная", T, depth - T, z0, inner_w, T, height,
                         back_material, note="ЛДСП 16 мм, набивная"))
    else:
        parts.append(box("задняя стенка ХДФ в паз", T, depth - GROOVE, z0, inner_w, BACK, height,
                         back_material, note="ХДФ 3 мм, паз 16 мм от заднего края"))

    if shelf_count > 0:
        span = height - 2 * T
        step = span / (shelf_count + 1)
        for i in range(shelf_count):
            z = z0 + T + step * (i + 1) - T / 2
            parts.append(box(f"полка {i + 1}", T, 0, z, inner_w, inner_d - shelf_inset, T,
                             material, edge="кромка ПВХ 0,4 мм по фасаду",
                             note="полкодержатели"))
    return parts


def _handle(x: float, y: float, z: float, horizontal: bool = True) -> Part:
    """Ручка 96 мм (техничка п.1/п.14) — маленький металлический брус."""
    if horizontal:
        return box("ручка 96 мм", x, y, z, 96.0, 12.0, 12.0, "metal",
                   note="ручка 96 мм (скоба/бабочка/рейлинг)")
    return box("ручка 96 мм", x, y, z, 12.0, 12.0, 96.0, "metal",
               note="ручка 96 мм (скоба/бабочка/рейлинг)")


def _facades(
    width: float,
    zone_z0: float,
    zone_h: float,
    doors: int,
    drawer_heights: list[float],
    *,
    material: str,
    niche_h: float = 0.0,
) -> list[Part]:
    """Накладные фасады. Ящики — сверху (техничка п.1), дверь/двери — ниже.

    Высоты ящиков приходят из прайса сверху вниз.
    """
    if doors <= 0 and not drawer_heights:
        return []
    parts: list[Part] = []
    door_zone_h = zone_h - niche_h
    drawers = list(drawer_heights)
    weights = list(reversed(drawers))  # снизу вверх: последний ящик прайса — нижний
    if doors > 0:
        gaps = GAP * (len(drawers) + 1)
        rest = door_zone_h - gaps - sum(drawers)
        door_weight = rest if rest > 150 else max(120.0, door_zone_h * 0.6)
        weights = [door_weight] + weights
    heights = facade_stack(door_zone_h, weights)

    z = zone_z0 + GAP
    drawer_no = len(drawers)
    for i, h in enumerate(heights):
        is_door = doors > 0 and i == 0
        if is_door:
            door_w = (width - GAP * (doors + 1)) / doors
            for d in range(doors):
                x = GAP + d * (door_w + GAP)
                parts.append(box(f"фасад (дверь {d + 1})", x, -FACADE_T, z, door_w, FACADE_T, h,
                                 material, edge="кромка 2,0 мм по периметру",
                                 note="петли Boyard 2 шт., ручка 96 мм"))
                handle_x = x + door_w / 2 - 48 if doors > 1 else x + door_w / 2 - 48
                handle_z = z + h - 80
                if h < 200:  # низкие дверцы — ручка по центру по высоте
                    handle_z = z + h / 2 - 6
                parts.append(_handle(handle_x, -FACADE_T - 12, min(handle_z, z + h - 20)))
        else:
            parts.append(box(f"фасад ящика {drawer_no}", GAP, -FACADE_T, z, width - 2 * GAP, FACADE_T, h,
                             material, edge="кромка 2,0 мм по периметру",
                             note="крепление на эксцентрики, ручка 96 мм"))
            parts.append(_handle(width / 2 - 48, -FACADE_T - 12, z + h / 2 - 6))
            drawer_no -= 1
        z += h + GAP
    return parts


def _drawer_boxes(width: float, depth: float, heights: list[float], z0: float, material: str) -> list[Part]:
    """Корпуса ящиков НПВ: дно ХДФ, глубина 450 мм, высота по таблице технички."""
    parts: list[Part] = []
    box_w = width - 2 * T - 26  # зазор под направляющие
    box_d = min(DRAWER_DEPTH, depth - 40)
    z = z0 + GAP
    for i, facade_h in enumerate(heights):
        body_h = drawer_body_height(facade_h)
        parts.append(box(f"дно ящика {i + 1}", T + 13, GROOVE, z, box_w, box_d, BACK,
                         "visma_hdf_back", note="ХДФ в паз"))
        parts.append(box(f"царга передняя {i + 1}", T + 13, GROOVE, z, box_w, T, body_h, material))
        parts.append(box(f"царга задняя {i + 1}", T + 13, GROOVE + box_d - T, z, box_w, T, body_h, material))
        parts.append(box(f"царга левая {i + 1}", T + 13, GROOVE, z, T, box_d, body_h, material))
        parts.append(box(f"царга правая {i + 1}", T + 13 + box_w - T, GROOVE, z, T, box_d, body_h, material))
        z += facade_h + GAP
    return parts


def build_visma_parts(m: dict) -> list[Part]:
    """Собрать детали модуля по записи каталога (`data/visma-modules.json`)."""
    w, h, d = m["width"], m["height"], m["depth"]
    kind = m["kind"]
    doors = int(m["doors"])
    drawer_heights = [float(x) for x in m.get("drawer_facade_heights") or []]
    shelves = int(m["shelves"])
    niche = float(m.get("niche_h") or 0.0)

    body = "visma_ldsp_body"
    back_mat = "visma_ldsp_back" if m.get("back_panel", "").startswith("набивная") else "visma_hdf_back"
    back_mode = "набивная" if m.get("back_panel", "").startswith("набивная") else "паз"
    facade_mat = "visma_facade"

    parts: list[Part] = []

    if kind == "base":
        legs = float(m.get("legs") or LEG)
        carcass_z = legs
        # опоры 4 шт.
        for i, (x, y) in enumerate(
            ((20, 20), (w - 60, 20), (20, d - 60), (w - 60, d - 60))
        ):
            parts.append(box(f"опора {i + 1}", x, y, 0, 40, 40, legs, "visma_leg",
                             note="опора регулируемая h100, отдельная позиция прайса"))
        # цоколь ЛДСП 95 мм, заглубление 18 мм от переда каркаса
        plinth_h = float(m.get("plinth") or PLINTH_H)
        parts.append(box("цоколь ЛДСП", 0, PLINTH_SETBACK, 0, w, T, plinth_h, "visma_plinth",
                         note="цоколь 95 мм, заглубление 18 мм от переда каркаса"))
    else:
        carcass_z = 0.0
        plinth_h = 0.0

    parts += _carcass(
        w, h, d,
        z0=carcass_z,
        shelf_count=shelves,
        shelf_inset=20.0,
        back=back_mode,
        material=body,
        back_material=back_mat,
    )
    parts += _facades(w, carcass_z, h, doors, drawer_heights, material=facade_mat, niche_h=niche)
    if drawer_heights:
        parts += _drawer_boxes(w, d, drawer_heights, carcass_z, body)
    return parts


def module_facade_area(parts: list[Part]) -> float:
    """Площадь фасадов в м² (по передним плоскостям деталей-фасадов)."""
    area = 0.0
    for part in parts:
        if not part.name.startswith("фасад"):
            continue
        dx, dy, dz = part.size
        area += (dx * dz) / 1_000_000.0
    return area


def module_stats(parts: list[Part]) -> dict:
    """Площадь ЛДСП, длина кромки, количество деталей — для спецификации."""
    ldsp_area = 0.0
    edge_m = 0.0
    for part in parts:
        dx, dy, dz = part.size
        sides = sorted((dx, dy, dz), reverse=True)
        if part.material.startswith("visma_leg"):
            continue
        area = sides[0] * sides[1] / 1_000_000.0
        if part.material.startswith("visma_ldsp") or part.material.startswith("visma_hdf") \
                or part.material.startswith("visma_plinth"):
            ldsp_area += area
        if part.edge:
            edge_m += 2 * (sides[0] + sides[1]) / 1000.0
    return {
        "parts": len(parts),
        "ldsp_m2": round(ldsp_area, 3),
        "edge_m": round(edge_m, 2),
        "facade_m2": round(module_facade_area(parts), 3),
    }
