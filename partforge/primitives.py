"""Примитивы и булевы операции. Единицы — миллиметры, Z вверх."""

from __future__ import annotations

import math

import numpy as np
import trimesh
from shapely.geometry import Polygon


def _clean(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Убрать вырожденные треугольники и дубли вершин (иначе STL не герметичен)."""
    mesh.merge_vertices()
    try:
        mask = mesh.nondegenerate_faces()
        if mask is not None and not mask.all():
            mesh.update_faces(mask)
    except Exception:
        pass
    try:
        mesh.remove_unreferenced_vertices()
    except Exception:
        pass
    return mesh


def box(size: tuple[float, float, float], center: tuple[float, float, float] = (0, 0, 0)) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=size)
    mesh.apply_translation(center)
    return mesh


def rounded_box(
    size: tuple[float, float, float],
    radius: float = 2.0,
    center: tuple[float, float, float] = (0, 0, 0),
    sections: int = 24,
) -> trimesh.Trimesh:
    """Плита с закруглёнными вертикальными рёбрами (радиус по контуру XY)."""
    sx, sy, sz = size
    radius = max(0.05, min(radius, min(sx, sy) / 2 - 0.05))
    profile = Polygon(
        trimesh.path.polygons.Polygon if False else _rounded_rect_points(sx, sy, radius, sections)
    )
    mesh = trimesh.creation.extrude_polygon(profile, height=sz)
    mesh.apply_translation((-sx / 2, -sy / 2, -sz / 2))
    mesh.apply_translation(center)
    return _clean(mesh)


def _rounded_rect_points(sx: float, sy: float, radius: float, sections: int) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    corners = [
        (sx - radius, sy - radius, 0.0),
        (radius, sy - radius, 90.0),
        (radius, radius, 180.0),
        (sx - radius, radius, 270.0),
    ]
    for cx, cy, start in corners:
        for i in range(sections + 1):
            angle = math.radians(start + 90.0 * i / sections)
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


def cylinder(
    radius: float,
    height: float,
    center: tuple[float, float, float] = (0, 0, 0),
    axis: str = "z",
    sections: int = 64,
) -> trimesh.Trimesh:
    mesh = trimesh.creation.cylinder(radius=radius, height=height, sections=sections)
    if axis == "x":
        mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    elif axis == "y":
        mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    mesh.apply_translation(center)
    return mesh


def tube(
    outer_d: float,
    inner_d: float,
    height: float,
    center: tuple[float, float, float] = (0, 0, 0),
    sections: int = 64,
) -> trimesh.Trimesh:
    outer = cylinder(outer_d / 2, height, center, sections=sections)
    inner = cylinder(inner_d / 2, height + 2, center, sections=sections)
    return _clean(outer.difference(inner))


def hollow_box(
    outer: tuple[float, float, float],
    wall: float,
    open_top: bool = True,
    open_front: bool = False,
    center: tuple[float, float, float] = (0, 0, 0),
    floor: float | None = None,
) -> trimesh.Trimesh:
    """Коробка с толщиной стенки; open_top/open_front — открытые стороны."""
    sx, sy, sz = outer
    shell = box(outer)
    inner = (
        sx - 2 * wall,
        sy - (0 if open_front else 2 * wall),
        sz - (0 if open_top else wall) - (floor if floor is not None else wall),
    )
    offset = (
        0.0,
        0.0 if open_front else 0.0,
        -sz / 2 + wall + inner[2] / 2 + (0.0 if open_top else 0.0),
    )
    cutter = box(inner, offset)
    if open_front:
        cutter.apply_translation((0, -wall, 0))
    if open_top:
        cutter.apply_translation((0, 0, wall / 2))
    result = _clean(shell.difference(cutter))
    result.apply_translation(center)
    return result


def extrude(points: list[tuple[float, float]], height: float, holes: list[list[tuple[float, float]]] | None = None) -> trimesh.Trimesh:
    """Выдавить 2D-контур (можно с отверстиями) в твердое тело."""
    outer = Polygon(points)
    if not outer.is_valid:
        outer = outer.buffer(0)
    for hole in holes or []:
        outer = outer.difference(Polygon(hole))
    if outer.geom_type == "MultiPolygon":
        # если отверстие задело край контура — берём самый большой кусок
        outer = max(outer.geoms, key=lambda g: g.area)
    mesh = trimesh.creation.extrude_polygon(outer, height=height)
    return _clean(mesh)


def prism_from_outline(
    outline: list[tuple[float, float]],
    thickness: float,
    center: tuple[float, float, float] = (0, 0, 0),
) -> trimesh.Trimesh:
    """Профиль (например, боковой вид клипсы) → тело постоянной толщины."""
    mesh = extrude(outline, thickness)
    mesh.apply_translation((-thickness / 2, 0, 0))
    mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    mesh.apply_translation(center)
    return mesh


def lathe(profile: list[tuple[float, float]], sections: int = 64) -> trimesh.Trimesh:
    """Тело вращения вокруг оси Z по профилю [(r, z), ...] снизу вверх.

    Профиль должен начинаться и заканчиваться при r = 0 (замкнутое тело):
    так получаются заглушки, штифты, втулки, ручки — одной герметичной сеткой.
    """
    if profile[0][0] > 1e-9 or profile[-1][0] > 1e-9:
        raise ValueError("профиль должен начинаться и заканчиваться при r = 0")

    angles = [2 * math.pi * i / sections for i in range(sections)]
    verts: list[tuple[float, float, float]] = []
    rings: list[list[int]] = []
    for r, z in profile:
        if r <= 1e-9:
            idx = len(verts)
            verts.append((0.0, 0.0, z))
            rings.append([idx])
        else:
            ring = []
            for a in angles:
                ring.append(len(verts))
                verts.append((r * math.cos(a), r * math.sin(a), z))
            rings.append(ring)

    faces: list[tuple[int, int, int]] = []
    for lower, upper in zip(rings, rings[1:]):
        if len(lower) == 1 and len(upper) == 1:
            continue
        if len(lower) == 1:
            center = lower[0]
            for i in range(sections):
                a, b = upper[i], upper[(i + 1) % sections]
                faces.append((center, a, b))
        elif len(upper) == 1:
            center = upper[0]
            for i in range(sections):
                a, b = lower[i], lower[(i + 1) % sections]
                faces.append((a, b, center))
        else:
            for i in range(sections):
                a0, a1 = lower[i], lower[(i + 1) % sections]
                b0, b1 = upper[i], upper[(i + 1) % sections]
                faces.append((a0, b0, b1))
                faces.append((a0, b1, a1))

    mesh = trimesh.Trimesh(vertices=np.array(verts), faces=np.array(faces), process=True)
    mesh.fix_normals()
    return _clean(mesh)


def union(*meshes: trimesh.Trimesh) -> trimesh.Trimesh:
    result = meshes[0]
    for mesh in meshes[1:]:
        result = result.union(mesh)
    return _clean(result)


def difference(mesh: trimesh.Trimesh, *cutters: trimesh.Trimesh) -> trimesh.Trimesh:
    result = mesh.difference(cutters[0])
    for cutter in cutters[1:]:
        result = result.difference(cutter)
    return _clean(result)


def intersection(a: trimesh.Trimesh, b: trimesh.Trimesh) -> trimesh.Trimesh:
    return _clean(a.intersection(b))


def mirror_y(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    out = mesh.copy()
    out.apply_transform(np.diag([1, -1, 1, 1]))
    out.invert()
    return _clean(out)
