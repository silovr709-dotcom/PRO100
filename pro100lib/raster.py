"""Растеризатор с z-buffer для миниатюр (чистый Python + Pillow).

Алгоритм художника не годится для корпусной мебели: высокая внутренняя полка
по глубине «ближе» к камере, чем низкая боковина, и рисуется поверх неё.
Поэтому здесь настоящий z-buffer: треугольники растеризуются с проверкой
глубины, а фасады выводятся вторым проходом с прозрачностью — так видно
наполнение закрытого шкафа и при этом ничего не «просвечивает» сквозь боковины.
"""

from __future__ import annotations

import math
from pathlib import Path

from .geometry import Part
from .materials import MATERIALS

COS30 = math.cos(math.radians(30))
SIN30 = math.sin(math.radians(30))
LIGHT = (-0.42, -0.52, 0.74)
FORWARD = (0.5, -0.5, 0.7071)


def _norm(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


LIGHT = _norm(LIGHT)
FORWARD = _norm(FORWARD)
RIGHT = _norm((1.0, 1.0, 0.0))
UP = _norm((-0.5, 0.5, 0.7071))


def _project(v, center):
    """Ортографическая проекция: экранные x/y и глубина вдоль взгляда."""
    d = (v[0] - center[0], v[1] - center[1], v[2] - center[2])
    sx = sum(a * b for a, b in zip(d, RIGHT))
    sy = sum(a * b for a, b in zip(d, UP))
    depth = sum(a * b for a, b in zip(d, FORWARD))
    return sx, -sy, depth


def _triangles(parts: list[Part]):
    verts = [v for p in parts for f in p.faces for v in f.verts]
    center = (
        (min(v[0] for v in verts) + max(v[0] for v in verts)) / 2,
        (min(v[1] for v in verts) + max(v[1] for v in verts)) / 2,
        (min(v[2] for v in verts) + max(v[2] for v in verts)) / 2,
    )
    tris = []
    for part in parts:
        material = MATERIALS.get(part.material)
        base = material.color if material else (0.7, 0.7, 0.7)
        is_facade = part.name.startswith("фасад")
        for face in part.faces:
            facing = sum(a * b for a, b in zip(face.normal, FORWARD))
            if facing <= 0.001:
                continue
            shade = max(0.0, sum(a * b for a, b in zip(face.normal, LIGHT)))
            factor = 0.55 + 0.45 * shade
            color = tuple(int(min(1.0, max(0.0, c * factor)) * 255) for c in base)
            pts = [_project(v, center) for v in face.verts]
            for i in range(1, len(pts) - 1):
                tris.append((pts[0], pts[i], pts[i + 1], color, is_facade))
    return tris


def _bbox(tri):
    xs = [p[0] for p in tri[:3]]
    ys = [p[1] for p in tri[:3]]
    return min(xs), max(xs), min(ys), max(ys)


def rasterize(parts: list[Part], size: int = 512, facade_alpha: int = 150, background=(244, 244, 242)):
    """Вернуть «сырое» RGB-изображение (bytes) и его размер."""
    tris = _triangles(parts)
    if not tris:
        return bytes(background) * (size * size), size

    xs = [p[0] for t in tris for p in t[:3]]
    ys = [p[1] for t in tris for p in t[:3]]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    span = max(max_x - min_x, max_y - min_y) or 1.0
    scale = 0.9 * size / span
    off_x = (size - (max_x - min_x) * scale) / 2 - min_x * scale
    off_y = (size - (max_y - min_y) * scale) / 2 - min_y * scale

    zbuf = [-1e18] * (size * size)
    color = bytearray(bytes(background) * (size * size))

    def draw(tri_list, alpha: int):
        for a, b, c, rgb, _ in tri_list:
            ax, ay = a[0] * scale + off_x, a[1] * scale + off_y
            bx, by = b[0] * scale + off_x, b[1] * scale + off_y
            cx, cy = c[0] * scale + off_x, c[1] * scale + off_y
            area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
            if abs(area) < 1e-9:
                continue
            x0 = max(0, int(min(ax, bx, cx)))
            x1 = min(size - 1, int(max(ax, bx, cx)) + 1)
            y0 = max(0, int(min(ay, by, cy)))
            y1 = min(size - 1, int(max(ay, by, cy)) + 1)
            if x0 > x1 or y0 > y1:
                continue
            inv = 1.0 / area
            for py in range(y0, y1 + 1):
                row = py * size
                fy = py + 0.5
                for px in range(x0, x1 + 1):
                    fx = px + 0.5
                    w0 = ((bx - ax) * (fy - ay) - (fx - ax) * (by - ay)) * inv
                    w1 = ((fx - ax) * (cy - ay) - (cx - ax) * (fy - ay)) * inv
                    w2 = 1.0 - w0 - w1
                    if w0 < 0 or w1 < 0 or w2 < 0:
                        continue
                    depth = a[2] * w2 + b[2] * w1 + c[2] * w0
                    idx = row + px
                    if depth <= zbuf[idx]:
                        continue
                    if alpha >= 255:
                        zbuf[idx] = depth
                        o = idx * 3
                        color[o] = rgb[0]
                        color[o + 1] = rgb[1]
                        color[o + 2] = rgb[2]
                    else:
                        # прозрачный фасад: смешиваем, но не перекрываем то,
                        # что уже нарисовано ближе к камере
                        o = idx * 3
                        k = alpha / 255.0
                        color[o] = int(color[o] * (1 - k) + rgb[0] * k)
                        color[o + 1] = int(color[o + 1] * (1 - k) + rgb[1] * k)
                        color[o + 2] = int(color[o + 2] * (1 - k) + rgb[2] * k)

    opaque = [t for t in tris if not t[4]]
    transparent = [t for t in tris if t[4]]
    draw(opaque, 255)
    if transparent:
        draw(transparent, facade_alpha if facade_alpha < 255 else 255)
    return bytes(color), size


def render_png(path: Path, parts: list[Part], size: int = 512, facade_alpha: int = 150) -> Path | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    raw, sz = rasterize(parts, size=size, facade_alpha=facade_alpha)
    image = Image.frombytes("RGB", (sz, sz), raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, quality=90)
    return path
