"""Экспорт набора деталей в OBJ + MTL (формат, который импортирует PRO100 5.20+)."""

from __future__ import annotations

from pathlib import Path

from .geometry import Part
from .materials import MATERIALS


def write_obj(path: Path, parts: list[Part], mtl_name: str, object_name: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# pro100lib export",
        f"# object: {object_name}",
        f"mtllib {mtl_name}",
    ]
    v_index = vt_index = vn_index = 1
    for part in parts:
        lines.append(f"o {_safe(part.name)}")
        lines.append(f"g {_safe(part.material)}")
        lines.append("s off")
        for face in part.faces:
            for vx, vy, vz in face.verts:
                lines.append(f"v {vx:.3f} {vy:.3f} {vz:.3f}")
            for u, v in face.uvs:
                lines.append(f"vt {u:.4f} {v:.4f}")
            lines.append(f"vn {face.normal[0]:.0f} {face.normal[1]:.0f} {face.normal[2]:.0f}")
        lines.append(f"usemtl {part.material}")
        for _ in part.faces:
            # каждая грань = 4 вершины (quad), у каждой свои vt и vn
            f = (
                f"f {v_index}/{vt_index}/{vn_index} "
                f"{v_index + 1}/{vt_index + 1}/{vn_index} "
                f"{v_index + 2}/{vt_index + 2}/{vn_index} "
                f"{v_index + 3}/{vt_index + 3}/{vn_index}"
            )
            lines.append(f)
            v_index += 4
            vt_index += 4
            vn_index += 1
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_mtl(path: Path, used_materials: set[str]) -> Path:
    lines: list[str] = []
    for key in sorted(used_materials):
        material = MATERIALS[key]
        r, g, b = material.color
        lines.append(f"newmtl {key}")
        lines.append(f"Kd {r:.4f} {g:.4f} {b:.4f}")
        lines.append("Ka 0.2000 0.2000 0.2000")
        lines.append("Ks 0.0500 0.0500 0.0500")
        lines.append("Ns 10.0")
        lines.append("illum 2")
        lines.append("d 1.0")
        if material.texture:
            lines.append(f"map_Kd {material.texture}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _safe(name: str) -> str:
    """Имена групп в OBJ — без пробелов и не-ASCII (совместимость с PRO100)."""
    translit = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
        "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
        "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
        "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
        "я": "ya", " ": "_", "-": "_",
    }
    out = []
    for ch in name.lower():
        if ch in translit:
            out.append(translit[ch])
        elif ch.isalnum() or ch == "_":
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip("_") or "part"
