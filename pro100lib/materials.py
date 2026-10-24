"""Простые материалы (ЛДСП, МДФ, ХДФ) и процедурные текстуры PNG.

Текстуры рисуются кодом, чтобы не тащить в репозиторий бинарные картинки.
Каждая текстура — 256x256 PNG, тайлится.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Material:
    key: str                    # имя в OBJ (usemtl)
    title: str                  # человекочитаемое название
    color: tuple[float, float, float]
    texture: str | None = None  # имя PNG-файла, если нужна текстура
    density: float = 0.0        # кг/м3, для расчёта веса в спецификации


MATERIALS: dict[str, Material] = {
    "ldsp_white": Material("ldsp_white", "ЛДСП белый 16 мм", (0.93, 0.93, 0.91), "ldsp_white.png", 700),
    "ldsp_oak": Material("ldsp_oak", "ЛДСП дуб сонома 16 мм", (0.72, 0.55, 0.38), "ldsp_oak.png", 700),
    "mdf_facade": Material("mdf_facade", "МДФ фасад 18 мм", (0.86, 0.85, 0.82), "mdf_facade.png", 750),
    "hdf_back": Material("hdf_back", "ХДФ 3 мм (задняя стенка)", (0.80, 0.78, 0.74), None, 850),
    "plinth": Material("plinth", "Плинтус/цоколь", (0.45, 0.45, 0.46), None, 700),
    "metal": Material("metal", "Металл (ручки, опоры)", (0.55, 0.56, 0.58), None, 7850),
    # --- материалы по техничке ВИСМА (ЛДСП 1-й категории, ХДФ белая, цоколь ЛДСП) ---
    "visma_ldsp_body": Material("visma_ldsp_body", "ЛДСП ВИСМА 16 мм, 1 кат. (корпус)", (0.88, 0.86, 0.82), None, 700),
    "visma_ldsp_back": Material("visma_ldsp_back", "ЛДСП 16 мм (задняя стенка виницы)", (0.86, 0.84, 0.80), None, 700),
    "visma_hdf_back": Material("visma_hdf_back", "ХДФ 3 мм белая (задняя стенка в паз)", (0.94, 0.93, 0.90), None, 850),
    "visma_facade": Material("visma_facade", "Фасад МДФ 16 мм в плёнке ПВХ", (0.965, 0.955, 0.925), None, 750),
    "visma_plinth": Material("visma_plinth", "Цоколь ЛДСП 16 мм (в цвет корпуса)", (0.80, 0.79, 0.76), None, 700),
    "visma_leg": Material("visma_leg", "Опора регулируемая ПВХ h100 (чёрная)", (0.18, 0.18, 0.19), None, 1100),
}


def _lcg(seed: int):
    state = seed & 0xFFFFFFFF

    def rnd() -> float:
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF

    return rnd


def _png_bytes(width: int, height: int, pixels: bytes) -> bytes:
    """Минимальный PNG-энкодер (RGB, 8 бит)."""
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)  # filter type 0
        raw.extend(pixels[y * stride : (y + 1) * stride])

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def _wood_texture(base: tuple[float, float, float], seed: int, size: int = 256) -> bytes:
    rnd = _lcg(seed)
    pixels = bytearray()
    grain = [rnd() for _ in range(size)]
    for y in range(size):
        for x in range(size):
            # волокна вдоль оси Y + мягкий шум
            wave = 0.5 + 0.5 * ((x + int(6 * grain[y % size])) % 24 < 12)
            n = 0.90 + 0.20 * grain[(x * 7 + y * 13) % size]
            shade = 0.82 + 0.16 * wave
            pixels.extend(
                int(max(0.0, min(1.0, c * shade * n)) * 255) for c in base
            )
    return _png_bytes(size, size, bytes(pixels))


def _flat_texture(base: tuple[float, float, float], seed: int, size: int = 64) -> bytes:
    rnd = _lcg(seed)
    pixels = bytearray()
    for _ in range(size * size):
        n = 0.97 + 0.06 * rnd()
        pixels.extend(int(max(0.0, min(1.0, c * n)) * 255) for c in base)
    return _png_bytes(size, size, bytes(pixels))


def write_textures(out_dir: Path, used: set[str]) -> dict[str, Path]:
    """Сгенерировать PNG-текстуры для использованных материалов."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    seeds = {"ldsp_white": 11, "ldsp_oak": 27, "mdf_facade": 41}
    for key in used:
        material = MATERIALS[key]
        if not material.texture:
            continue
        target = out_dir / material.texture
        if key == "ldsp_oak":
            data = _wood_texture((0.70, 0.52, 0.34), seeds.get(key, 1))
        elif key == "mdf_facade":
            data = _flat_texture(material.color, seeds.get(key, 1))
        else:
            data = _flat_texture(material.color, seeds.get(key, 1), size=64)
        target.write_bytes(data)
        written[key] = target
    return written
