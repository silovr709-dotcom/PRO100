"""Библиотека параметрических деталей.

Каждая функция принимает словарь параметров (мм) и возвращает trimesh-тело.
Все размеры подобраны так, чтобы деталь печаталась без поддержек:
плоская сторона на столе, стенки ≥ 1.2 мм, отверстия с допуском принтера.
"""

from __future__ import annotations

import math

import trimesh

from .primitives import box, cylinder, difference, extrude, lathe, rounded_box, union


def led_clip(p: dict) -> trimesh.Trimesh:
    """Пружинная клипса-зажим (U-профиль) с отверстием под саморез.

    Профиль выдавливается по длине ленты: деталь печатается лёжа на базе,
    без поддержек. Зажим держит за счёт упругости боковин (натяг 0.1–0.2 мм).
    """
    strip_w = float(p.get("strip_width", 10.0))
    strip_h = float(p.get("strip_height", 4.0))
    wall = float(p.get("wall", 1.6))
    base_t = float(p.get("base_thickness", 2.0))
    length = float(p.get("length", 16.0))
    clearance = float(p.get("clearance", 0.1))
    interference = float(p.get("interference", 0.1))   # натяг: стенки чуть уже ленты
    hole_d = float(p.get("screw_hole_d", 3.4))
    hole_offset = float(p.get("screw_offset", 3.0))

    inner_w = strip_w + clearance - interference
    outer_w = inner_w + 2 * wall
    cavity_h = strip_h + clearance
    height = base_t + cavity_h

    # U-профиль в плоскости (x, z): база + две боковины, карман открыт вверх
    outline = [
        (-outer_w / 2, 0.0),
        (outer_w / 2, 0.0),
        (outer_w / 2, height),
        (inner_w / 2, height),
        (inner_w / 2, base_t),
        (-inner_w / 2, base_t),
        (-inner_w / 2, height),
        (-outer_w / 2, height),
    ]
    hole_c = (0.0, base_t / 2)
    hole_poly = [
        (hole_c[0] + (hole_d / 2) * math.cos(a), hole_c[1] + (hole_d / 2) * math.sin(a))
        for a in [2 * math.pi * i / 48 for i in range(48)]
    ]
    body = extrude(outline, length, holes=[hole_poly])
    # профиль в XY выдавливали по Z; поворачиваем так, чтобы длина легла по Y, а профиль — в XZ
    body.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-90), [1, 0, 0]))
    body.apply_translation((0, length / 2, 0))
    body.apply_translation((0, 0, -body.bounds[0][2]))
    return body


def tolerance_coupon(p: dict) -> trimesh.Trimesh:
    """Тест-купон принтера: отверстия, пазы, штифт и мост.

    Печатается один раз на новом принтере/пластике: показывает, какой зазор
    нужен, чтобы деталь села плотно, но без молотка.
    """
    w = float(p.get("width", 70.0))
    d = float(p.get("depth", 46.0))
    t = float(p.get("thickness", 4.0))
    holes = [float(x) for x in p.get("holes", [3.0, 4.0, 5.0, 6.0, 8.0])]
    slots = [float(x) for x in p.get("slots", [0.2, 0.3, 0.4, 0.5])]
    pin_d = float(p.get("pin_d", 5.0))

    plate = rounded_box((w, d, t), radius=2.0, center=(0, 0, t / 2))

    step = (w - 12) / max(1, len(holes))
    for i, dia in enumerate(holes):
        x = -w / 2 + 6 + step * (i + 0.5)
        cut = cylinder(dia / 2, t + 2, center=(x, d / 2 - 9, t / 2))
        plate = difference(plate, cut)

    for i, width in enumerate(slots):
        x = -w / 2 + 6 + step * (i + 0.5)
        cut = box((width, 14, t + 2), center=(x, -d / 2 + 12, t / 2))
        plate = difference(plate, cut)

    # штифт-проверка посадки
    pin = cylinder(pin_d / 2, 10, center=(0, 0, t + 5))
    # мост: два столбика и перекладина
    bridge_span = float(p.get("bridge_span", 14.0))
    pillars = []
    for sign in (-1, 1):
        pillar = box((4, 4, 10), center=(sign * bridge_span / 2, d / 2 - 9, t + 5))
        pillars.append(pillar)
    bridge = box((bridge_span + 4, 4, 3), center=(0, d / 2 - 9, t + 10 + 1.5))

    model = union(plate, pin, *pillars, bridge)
    model.apply_translation((0, 0, -model.bounds[0][2]))
    return model


def hole_plug(p: dict) -> trimesh.Trimesh:
    """Заглушка мебельного отверстия: ножка + грибок + фаска на входе.

    Строится телом вращения по профилю — одна герметичная сетка, без булевых
    склеек (они дают лишние оболочки).
    """
    hole_d = float(p.get("hole_d", 5.0))
    clearance = float(p.get("clearance", 0.25))
    depth = float(p.get("depth", 4.0))
    head_d = float(p.get("head_d", hole_d + 3.0))
    head_h = float(p.get("head_h", 1.2))
    slot = float(p.get("slot", 0.0))
    chamfer = float(p.get("chamfer", 0.5))

    stem_r = max(0.6, (hole_d - clearance) / 2)
    head_r = head_d / 2
    top = depth + head_h

    profile = [
        (0.0, 0.0),
        (max(0.2, stem_r - chamfer), 0.0),
        (stem_r, chamfer),
        (stem_r, depth),
        (head_r, depth),
        (head_r, top - 0.4),
        (head_r - 0.4, top),
        (0.0, top),
    ]
    plug = lathe(profile, sections=64)

    if slot > 0:
        cut = box((slot, stem_r * 2.5, depth * 0.85), center=(0, 0, depth * 0.85 / 2 - 0.1))
        plug = difference(plug, cut)
    plug.apply_translation((0, 0, -plug.bounds[0][2]))
    return plug


BUILDERS = {
    "led_clip": led_clip,
    "tolerance_coupon": tolerance_coupon,
    "hole_plug": hole_plug,
}
