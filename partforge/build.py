"""Сборка детали из JSON-спеки: модель → проверки → STL/3MF + превью + карточка."""

from __future__ import annotations

import json
from pathlib import Path

import trimesh

from .parts import BUILDERS
from .preview import render_sheet
from .report import print_estimate, print_report, readiness


def load_spec(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_from_spec(spec: dict, out_dir: Path | str, name: str | None = None) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    key = name or spec.get("name") or "part"
    part_type = spec["type"]
    if part_type not in BUILDERS:
        raise KeyError(f"неизвестный тип детали: {part_type}. Доступны: {', '.join(BUILDERS)}")

    params = spec.get("params", {})
    mesh = BUILDERS[part_type](params)

    stl = out / f"{key}.stl"
    mesh.export(stl)
    try:
        data = trimesh.exchange.threemf.export_3mf([mesh])
        if data:
            (out / f"{key}.3mf").write_bytes(data)
    except Exception:  # 3MF — опционально, STL всегда есть
        pass

    check = readiness(mesh, min_wall=float(spec.get("min_wall", 1.2)),
                      nozzle=float(spec.get("nozzle", 0.4)))
    estimate = print_estimate(
        mesh,
        material=spec.get("material", "pla"),
        infill=float(spec.get("infill", 0.2)),
        layer=float(spec.get("layer", 0.2)),
        price_per_kg=spec.get("price_per_kg"),
    )
    preview = render_sheet(mesh, out / f"{key}.png")

    card_lines = [
        f"# {spec.get('title', key)}",
        "",
        f"Тип: `{part_type}`, материал: {estimate['material'].upper()}, "
        f"сопло {check['nozzle']} мм, слой {estimate['layer_mm']} мм",
        "",
        "## Параметры",
        "",
        "| Параметр | Значение, мм |",
        "|---|---|",
    ]
    for pname, value in params.items():
        card_lines.append(f"| {pname} | {value} |")
    card_lines += [
        "",
        "## Проверка печати",
        "",
        "```",
        print_report(check, estimate),
        "```",
        "",
        "## Что делать дальше",
        "",
        f"1. Открыть `{key}.stl` в слайсере (Cura / PrusaSlicer / Orca).",
        "2. Ориентация: плоской стороной на стол, как на превью «спереди».",
        f"3. Заполнение {estimate['infill_pct']} %, слой {estimate['layer_mm']} мм, "
        "поддержки — только если в отчёте есть нависания.",
        "4. Первый раз печатать `tolerance_coupon`, чтобы подобрать зазор под свой принтер.",
        "",
        f"Превью: `{preview.name}`",
    ]
    (out / f"{key}.md").write_text("\n".join(card_lines), encoding="utf-8")

    summary = {
        "name": key,
        "title": spec.get("title", key),
        "type": part_type,
        "stl": str(stl),
        "preview": str(preview),
        "readiness": check,
        "estimate": estimate,
    }
    (out / f"{key}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
