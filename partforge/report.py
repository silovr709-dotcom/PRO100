"""Проверка печатаемости и оценка расхода/времени печати."""

from __future__ import annotations

import math

import numpy as np
import trimesh

DENSITY = {"pla": 1.24, "petg": 1.27, "abs": 1.04, "asa": 1.07, "tpu": 1.21, "nylon": 1.14}


def readiness(mesh: trimesh.Trimesh, *, min_wall: float = 1.2, nozzle: float = 0.4) -> dict:
    """Диагностика модели: герметичность, габариты, нависания, тонкие места."""
    mesh = mesh.copy()
    mesh.merge_vertices()

    watertight = bool(mesh.is_watertight)
    volume = float(mesh.volume)
    area = float(mesh.area)
    extents = [round(float(v), 2) for v in mesh.extents]
    body_count = len(mesh.split(only_watertight=False))

    # нависания: грани, наклонённые к столу больше 45°, КРОМЕ лежащих на столе
    normals = np.asarray(mesh.face_normals)
    areas = np.asarray(mesh.area_faces)
    face_z_min = np.asarray(mesh.triangles)[:, :, 2].min(axis=1)
    bed_z = float(mesh.bounds[0][2])
    on_bed = face_z_min <= bed_z + 0.15
    down = (normals[:, 2] < -math.cos(math.radians(45))) & ~on_bed
    overhang = float(areas[down].sum())
    flat_on_bed = float(areas[(np.abs(normals[:, 2] + 1) < 1e-3) & on_bed].sum())

    # оценка минимальной толщины: расстояние от каждой вершины до противоположной
    # поверхности вдоль инвертированной нормали (грубо, но ловит «фольгу»)
    thin = _thin_spots(mesh, min_wall)

    return {
        "watertight": watertight,
        "bodies": body_count,
        "volume_mm3": round(volume, 1),
        "volume_cm3": round(volume / 1000, 3),
        "area_mm2": round(area, 1),
        "extents_mm": extents,
        "overhang_mm2": round(overhang, 1),
        "overhang_pct": round(100 * overhang / area, 1) if area else 0.0,
        "bed_contact_mm2": round(flat_on_bed, 1),
        "thin_spots": thin,
        "min_wall_recommended": min_wall,
        "foil_risk": bool(thin),
        "nozzle": nozzle,
    }


def _thin_spots(mesh: trimesh.Trimesh, min_wall: float, sample: int = 4000) -> list[dict]:
    """Ищем места, где материал тоньше min_wall: стреляем внутрь по нормали."""
    verts = np.asarray(mesh.vertices)
    if len(verts) == 0:
        return []
    normals = np.asarray(mesh.vertex_normals)
    idx = np.arange(len(verts))
    if len(idx) > sample:
        idx = np.random.default_rng(0).choice(idx, size=sample, replace=False)
    origins = verts[idx] - normals[idx] * 0.05
    directions = -normals[idx]
    hits = mesh.ray.intersects_id(origins, directions, multiple_hits=False)
    # trimesh 5.x: возвращает (locations, ray_index, tri_index); старые — (locations, tri)
    locations, ray_index = (hits[0], hits[1]) if len(hits) == 3 else (hits[0], hits[1])
    if len(locations) == 0:
        return []
    distances = np.asarray(locations, dtype=float)
    origins = origins[np.asarray(ray_index)]
    if len(hits) == 3:
        pass
    close = np.where((distances > 0) & (distances < min_wall))[0]
    out = []
    seen = set()
    for i in close[:20]:
        point = tuple(round(float(c), 1) for c in origins[i])
        if point in seen:
            continue
        seen.add(point)
        out.append({"at_mm": point, "wall_mm": round(float(distances[i]), 2)})
    return out


def print_estimate(mesh: trimesh.Trimesh, material: str = "pla", infill: float = 0.2,
                   layer: float = 0.2, price_per_kg: float | None = None) -> dict:
    """Расход пластика и времени: оболочка 3 периметра + внутренность с заполнением."""
    volume = float(mesh.volume)
    area = float(mesh.area)
    shell_thickness = 1.2  # 3 периметра по 0.4
    shell_volume = min(volume, area * shell_thickness)
    infill_volume = max(0.0, volume - shell_volume) * infill
    solid = shell_volume + infill_volume
    density = DENSITY.get(material.lower(), 1.24)
    grams = solid / 1000 * density
    # время: объём extrusion / (ширина линии * слой * скорость)
    speed = 45.0  # мм/с
    flow = 0.42 * layer * speed  # мм³/с
    seconds = solid / flow + 120  # + прогрев/подготовка
    result = {
        "material": material,
        "infill_pct": int(infill * 100),
        "layer_mm": layer,
        "grams": round(grams, 1),
        "meters_filament_1_75": round(solid / (math.pi * (1.75 / 2) ** 2) / 1000, 2),
        "minutes": int(seconds / 60),
    }
    if price_per_kg:
        result["cost_rub"] = round(grams / 1000 * price_per_kg, 1)
    return result


def print_report(readiness_data: dict, estimate: dict | None = None) -> str:
    r = readiness_data
    lines = [
        f"Герметичность: {'OK' if r['watertight'] else 'ПРОБЛЕМА (дыры в сетке)'}",
        f"Тел в модели: {r['bodies']}",
        f"Габариты: {r['extents_mm'][0]} × {r['extents_mm'][1]} × {r['extents_mm'][2]} мм",
        f"Объём: {r['volume_cm3']} см³, площадь поверхности: {r['area_mm2']} мм²",
        f"Нависания >45°: {r['overhang_pct']} % площади"
        + (" (нужны поддержки)" if r["overhang_pct"] > 2 else " — поддержки почти не нужны"),
        f"Пятно контакта со столом: {r['bed_contact_mm2']} мм²"
        + ("  ⚠ мало, добавьте кайму/подложку" if 0 < r["bed_contact_mm2"] < 60 else ""),
    ]
    if r["foil_risk"]:
        lines.append(f"⚠ Тонкие места (< {r['min_wall_recommended']} мм): " +
                     ", ".join(f"{s['wall_mm']} мм в {s['at_mm']}" for s in r["thin_spots"][:5]))
    else:
        lines.append(f"Тонких стенок (< {r['min_wall_recommended']} мм) не найдено")
    if estimate:
        lines.append(
            f"Печать ({estimate['material'].upper()}, заполнение {estimate['infill_pct']} %): "
            f"≈{estimate['grams']} г, {estimate['meters_filament_1_75']} м прутка, "
            f"≈{estimate['minutes']} мин"
            + (f", {estimate['cost_rub']} ₽" if "cost_rub" in estimate else "")
        )
    return "\n".join(lines)
