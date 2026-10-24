"""CLI: python3 -m partforge build --spec spec.json --out out_parts"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .build import build_from_spec, load_spec
from .report import print_estimate, print_report, readiness


def cmd_build(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    summary = build_from_spec(spec, args.out)
    print(f"Модель: {summary['title']}")
    print(print_report(summary["readiness"], summary["estimate"]))
    print(f"STL: {summary['stl']}")
    print(f"Превью: {summary['preview']}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    import trimesh

    mesh = trimesh.load(args.file, force="mesh")
    print(print_report(readiness(mesh, min_wall=args.min_wall), print_estimate(mesh)))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Проверить все спеки в папке: собрать в память и убедиться, что тела валидны."""
    from .parts import BUILDERS

    ok = True
    for path in sorted(Path(args.dir).glob("*.json")):
        spec = load_spec(path)
        builder = BUILDERS.get(spec["type"])
        if builder is None:
            print(f"{path.name}: НЕИЗВЕСТНЫЙ тип {spec['type']}")
            ok = False
            continue
        mesh = builder(spec.get("params", {}))
        check = readiness(mesh)
        status = "OK" if check["watertight"] and check["bodies"] == 1 and not check["foil_risk"] else "ПРОВЕРИТЬ"
        print(f"{path.name:26s} {status:9s} {check['volume_cm3']:7.2f} см³  "
              f"{check['extents_mm'][0]}×{check['extents_mm'][1]}×{check['extents_mm'][2]} мм  "
              f"тел {check['bodies']}, нависания {check['overhang_pct']} %")
        ok = ok and status == "OK"
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="partforge", description="Детали под 3D-печать")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="собрать деталь по JSON-спеке")
    p_build.add_argument("--spec", required=True)
    p_build.add_argument("--out", default="out_parts")
    p_build.set_defaults(func=cmd_build)

    p_check = sub.add_parser("check", help="проверить готовый STL")
    p_check.add_argument("file")
    p_check.add_argument("--min-wall", type=float, default=1.2)
    p_check.set_defaults(func=cmd_check)

    p_val = sub.add_parser("validate", help="проверить все спеки")
    p_val.add_argument("--dir", default="partforge/specs")
    p_val.set_defaults(func=cmd_validate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
