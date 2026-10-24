"""Изометрический предпросмотр модуля (SVG всегда, JPG — если есть Pillow).

Нужен, чтобы проверять геометрию до импорта в PRO100 и чтобы у каждого модуля
была миниатюра рядом с моделью.

Камера смотрит на фасад: направления проецируются так, чтобы были видны
передняя плоскость (−Y), верх (+Z) и правая боковина (+X). Грани рисуются
алгоритмом художника по глубине вдоль луча зрения — иначе внутренние детали
перекрывают фасад.
"""

from __future__ import annotations

import math
from pathlib import Path

from .geometry import Part
from .materials import MATERIALS

COS30 = math.cos(math.radians(30))
SIN30 = math.sin(math.radians(30))
LIGHT = (-0.45, -0.55, 0.70)


def _screen(x: float, y: float, z: float, y_max: float) -> tuple[float, float]:
    """Изометрия «вид спереди-сверху-справа». Y зеркалим, чтобы фасад был к камере."""
    yy = y_max - y
    sx = (x - yy) * COS30
    sy = (x + yy) * SIN30 - z
    return sx, sy


def _depth(x: float, y: float, z: float, y_max: float) -> float:
    """Чем больше — тем ближе к камере."""
    return x + (y_max - y) + z


FacadePoly = tuple[float, tuple[int, int, int], list[tuple[float, float]], bool]


def _polygons(parts: list[Part]) -> tuple[list[FacadePoly], list[float]]:
    y_max = max((p.faces and max(v[1] for f in p.faces for v in f.verts)) or 0.0 for p in parts)
    light_norm = math.sqrt(sum(c * c for c in LIGHT))
    light = tuple(c / light_norm for c in LIGHT)

    polys = []
    for part in parts:
        material = MATERIALS.get(part.material)
        base = material.color if material else (0.7, 0.7, 0.7)
        for face in part.faces:
            pts = [_screen(*v, y_max) for v in face.verts]
            depth = sum(_depth(*v, y_max) for v in face.verts) / 4
            shade = max(0.0, sum(a * b for a, b in zip(face.normal, light)))
            factor = 0.55 + 0.45 * shade
            color = tuple(int(min(1.0, max(0.0, c * factor)) * 255) for c in base)
            is_facade = part.name.startswith("фасад")
            polys.append((depth, color, pts, is_facade))
    # грани фасадов рисуем последними и полупрозрачными — чтобы было видно наполнение
    polys.sort(key=lambda p: (p[3], p[0]))

    xs = [x for _, _, pts, _ in polys for x, _ in pts]
    ys = [y for _, _, pts, _ in polys for _, y in pts]
    bbox = [min(xs), max(xs), min(ys), max(ys)]
    return polys, bbox


def render_svg(parts: list[Part], title: str, width_px: int = 640, height_px: int = 560) -> str:
    polys, (min_x, max_x, min_y, max_y) = _polygons(parts)
    span = max(max_x - min_x, max_y - min_y) or 1.0
    top_margin = 56
    scale = 0.88 * min(width_px / span, (height_px - top_margin) / span)
    off_x = (width_px - (max_x - min_x) * scale) / 2 - min_x * scale
    off_y = top_margin + ((height_px - top_margin) - (max_y - min_y) * scale) / 2 - min_y * scale

    body = []
    for _, color, pts, is_facade in polys:
        moved = " ".join(f"{x * scale + off_x:.1f},{y * scale + off_y:.1f}" for x, y in pts)
        fill = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
        opacity = ' fill-opacity="0.45"' if is_facade else ""
        body.append(
            f'<polygon points="{moved}" fill="{fill}" stroke="{fill}" '
            f'stroke-width="0.7"{opacity}/>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{height_px}" '
        f'viewBox="0 0 {width_px} {height_px}">'
        f'<rect width="100%" height="100%" fill="#f4f4f2"/>'
        f'<text x="16" y="30" font-family="Segoe UI,Arial" font-size="18" fill="#222">{_esc(title)}</text>'
        + "".join(body)
        + "</svg>"
    )


def write_preview(path: Path, parts: list[Part], title: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_svg(parts, title), encoding="utf-8")
    return path


def render_jpg(path: Path, parts: list[Part], title: str, size: int = 512) -> Path | None:
    """Растровая миниатюра (нужен Pillow). Без Pillow возвращает None — SVG остаётся."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    polys, (min_x, max_x, min_y, max_y) = _polygons(parts)
    span = max(max_x - min_x, max_y - min_y) or 1.0
    scale = 0.90 * size / span
    off_x = (size - (max_x - min_x) * scale) / 2 - min_x * scale
    off_y = (size - (max_y - min_y) * scale) / 2 - min_y * scale

    image = Image.new("RGB", (size, size), (244, 244, 242))
    draw = ImageDraw.Draw(image)
    for _, color, pts, is_facade in polys:
        moved = [(x * scale + off_x, y * scale + off_y) for x, y in pts]
        if not is_facade:
            draw.polygon(moved, fill=color, outline=color)
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for _, color, pts, is_facade in polys:
        if not is_facade:
            continue
        moved = [(x * scale + off_x, y * scale + off_y) for x, y in pts]
        odraw.polygon(moved, fill=color + (120,), outline=color + (150,))
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, quality=90)
    return path


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
