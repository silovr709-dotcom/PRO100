"""Превью модели: 4 вида (изометрия, спереди, сверху, справа) в одну PNG.

Свой z-buffer на numpy: без OpenGL и без pyglet — работает в контейнере.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import trimesh

VIEWS = {
    "изометрия": ((1.0, -1.0, 0.85), None),
    "спереди (−Y)": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    "сверху": ((0.0, 0.0, 1.0), (0.0, -1.0, 0.0)),
    "справа": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
}
LIGHT = np.array([-0.35, -0.55, 0.75])


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    return v / (np.linalg.norm(v) or 1.0)


def _basis(direction, up_hint):
    forward = -_unit(direction)          # смотрит от камеры в сцену
    up_hint = np.asarray(up_hint if up_hint is not None else (0, 0, 1), dtype=float)
    if abs(np.dot(_unit(up_hint), forward)) > 0.99:
        up_hint = np.array([0.0, -1.0, 0.0])
    right = _unit(np.cross(up_hint, forward))
    up = _unit(np.cross(forward, right))
    return forward, right, up


def _render_view(mesh: trimesh.Trimesh, direction, up_hint, size: int) -> np.ndarray:
    forward, right, up = _basis(direction, up_hint)
    tris = np.asarray(mesh.triangles)          # (n, 3, 3)
    normals = np.asarray(mesh.face_normals)
    center = (mesh.bounds[0] + mesh.bounds[1]) / 2

    pts = (tris - center) @ np.stack([right, up, forward], axis=1)  # x=right, y=up, z=depth
    sx = pts[:, :, 0]
    sy = -pts[:, :, 1]
    depth = pts[:, :, 2].mean(axis=1)

    span = max(sx.max() - sx.min(), sy.max() - sy.min()) or 1.0
    scale = 0.92 * size / span
    ox = size / 2 - (sx.min() + sx.max()) / 2 * scale
    oy = size / 2 - (sy.min() + sy.max()) / 2 * scale
    px = sx * scale + ox
    py = sy * scale + oy

    visible = (normals @ forward) < 0
    shade = np.abs(normals @ _unit(LIGHT)) * 0.6 + 0.4
    base = np.array([205, 198, 186]) / 255.0
    colors = np.clip(base[None, :] * shade[:, None], 0, 1)
    colors = (colors * 255).astype(np.uint8)

    zbuf = np.full((size, size), -1e18)
    img = np.full((size, size, 3), 247, dtype=np.uint8)
    order = np.argsort(depth)
    for t in order[visible[order]]:
        x0, y0 = px[t, 0], py[t, 0]
        x1, y1 = px[t, 1], py[t, 1]
        x2, y2 = px[t, 2], py[t, 2]
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue
        minx = max(0, int(math.floor(min(x0, x1, x2))))
        maxx = min(size - 1, int(math.ceil(max(x0, x1, x2))))
        miny = max(0, int(math.floor(min(y0, y1, y2))))
        maxy = min(size - 1, int(math.ceil(max(y0, y1, y2))))
        if minx > maxx or miny > maxy:
            continue
        xs = np.arange(minx, maxx + 1) + 0.5
        ys = np.arange(miny, maxy + 1) + 0.5
        gx, gy = np.meshgrid(xs, ys)
        w0 = ((x1 - x0) * (gy - y0) - (gx - x0) * (y1 - y0)) / area
        w1 = ((gx - x0) * (y2 - y0) - (x2 - x0) * (gy - y0)) / area
        w2 = 1.0 - w0 - w1
        mask = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not mask.any():
            continue
        d = depth[t]
        sub_z = zbuf[miny : maxy + 1, minx : maxx + 1]
        upd = mask & (d >= sub_z)
        if not upd.any():
            continue
        sub_z[upd] = d
        sub_i = img[miny : maxy + 1, minx : maxx + 1]
        sub_i[upd] = colors[t]
    return img


def render_sheet(mesh: trimesh.Trimesh, out: Path, size: int = 460, labels: bool = True) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    views = [_render_view(mesh, d, up, size) for d, up in VIEWS.values()]
    cols = 2
    rows = 2
    pad = 8
    header = 42
    sheet = Image.new("RGB", (cols * (size + pad) + pad, rows * (size + pad) + pad + header), (250, 250, 248))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    extents = mesh.extents
    draw.text((12, 12), f"Габариты {extents[0]:.1f} × {extents[1]:.1f} × {extents[2]:.1f} мм",
              fill=(30, 30, 30), font=font)
    for i, (name, view) in enumerate(zip(VIEWS.keys(), views)):
        col, row = i % cols, i // cols
        x = pad + col * (size + pad)
        y = header + pad + row * (size + pad)
        sheet.paste(Image.fromarray(view), (x, y))
        if labels:
            draw.text((x + 8, y + 6), name, fill=(110, 110, 110), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=92)
    return out
