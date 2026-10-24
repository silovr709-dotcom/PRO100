"""CLI: python -m pro100lib <list|build|probe>"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .catalog import build_library
from .modules import MODULES


def cmd_list(_args: argparse.Namespace) -> int:
    for spec in MODULES:
        print(
            f"{spec.key:18s} {spec.category:16s} "
            f"{int(spec.width)}x{int(spec.height)}x{int(spec.depth)} мм  {spec.title}"
        )
    print(f"\nВсего модулей: {len(MODULES)}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    index = build_library(args.out)
    print(f"Готово: {args.out}")
    print(f"Модулей: {len(index['modules'])}, текстур: {len(index.get('textures', []))}")
    print(f"Индекс: {args.out / 'library.json'}")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    from tools.meb_probe import probe, verdict  # локальный импорт: скрипт из tools/

    report = probe(Path(args.file))
    report["verdict"] = verdict(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pro100lib", description="Библиотека модулей для PRO100")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="список модулей")
    p_list.set_defaults(func=cmd_list)

    p_build = sub.add_parser("build", help="собрать библиотеку в папку")
    p_build.add_argument("--out", type=Path, default=Path("library"), help="папка вывода (по умолчанию library/)")
    p_build.set_defaults(func=cmd_build)

    p_probe = sub.add_parser("probe", help="анализ .meb/.sto файла")
    p_probe.add_argument("file")
    p_probe.set_defaults(func=cmd_probe)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
