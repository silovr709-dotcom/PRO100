"""Геометрия: деталь-параллелепипед с UV по реальным размерам.

Единицы — миллиметры, ось Z — вверх, начало координат — левый-передний-нижний
угол модуля (X вправо, Y назад, Z вверх).
"""

from __future__ import annotations

from dataclasses import dataclass, field

UV_SCALE = 600.0  # мм на один повтор текстуры


@dataclass
class Face:
    verts: list[tuple[float, float, float]]
    normal: tuple[float, float, float]
    uvs: list[tuple[float, float]]


@dataclass
class Part:
    name: str
    material: str
    # габарит детали в мм (для спецификации/раскроя)
    size: tuple[float, float, float]
    faces: list[Face] = field(default_factory=list)
    note: str = ""
    edge: str = ""  # описание кромки, напр. "1,0 мм по периметру"


def _face(quad, normal, uv_wh):
    u, v = uv_wh
    uvs = [(0.0, 0.0), (u, 0.0), (u, v), (0.0, v)]
    return Face(verts=list(quad), normal=normal, uvs=uvs)


def box(
    name: str,
    x0: float,
    y0: float,
    z0: float,
    dx: float,
    dy: float,
    dz: float,
    material: str,
    note: str = "",
    edge: str = "",
) -> Part:
    """Прямоугольная деталь (плита) по минимальному углу и габаритам."""
    x1, y1, z1 = x0 + dx, y0 + dy, z0 + dz
    s = UV_SCALE
    faces = [
        # низ / верх
        _face([(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)], (0, 0, -1), (dx / s, dy / s)),
        _face([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], (0, 0, 1), (dx / s, dy / s)),
        # перед / зад
        _face([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], (0, -1, 0), (dx / s, dz / s)),
        _face([(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)], (0, 1, 0), (dx / s, dz / s)),
        # лево / право
        _face([(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)], (-1, 0, 0), (dy / s, dz / s)),
        _face([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], (1, 0, 0), (dy / s, dz / s)),
    ]
    return Part(name=name, material=material, size=(dx, dy, dz), faces=faces, note=note, edge=edge)
