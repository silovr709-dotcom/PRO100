#!/usr/bin/env python3
"""meb_probe.py — быстрый форензик-анализ файлов PRO100 (.meb / .sto).

Скрипт ничего не ломает и не патчит: он только читает файл и показывает,
что у него внутри — сигнатуру, энтропию, наличие сжатия/шифрования,
читаемые строки и т.п. Результат помогает понять, можно ли такой файл
сгенерировать/распарсить сторонним кодом.

Использование:
    python3 tools/meb_probe.py "google_drive/для передачи.meb"
    python3 tools/meb_probe.py file.meb --json report.json
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import re
import sys
import zlib
from pathlib import Path

# Алгоритмы, которые имеет смысл пробовать "в лоб".
try:  # pragma: no cover - необязательные зависимости
    import bz2
    import lzma
except ImportError:  # pragma: no cover
    bz2 = lzma = None  # type: ignore


KNOWN_SIGNATURES = {
    b"*D?\x03": "PRO100 .meb/.sto (Ecru Software), современный (5.x/6.x/7.x)",
    b"PSTO": "PRO100 .meb/.sto, старая версия (3.x/4.x) — в файле есть открытый текст",
    b"PK\x03\x04": "ZIP-контейнер",
    b"\x1f\x8b": "gzip",
    b"\x28\xb5\x2f\xfd": "zstd",
    b"7z\xbc\xaf": "7-Zip",
}


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = collections.Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def repeated_blocks(data: bytes, size: int) -> list[tuple[bytes, int]]:
    counts = collections.Counter(data[i : i + size] for i in range(len(data) - size + 1))
    return sorted(((k, v) for k, v in counts.items() if v > 1), key=lambda kv: -kv[1])


def try_decompress_offsets(data: bytes, max_offset: int = 16) -> list[dict]:
    """Пробуем распаковать данные с разных смещений разными алгоритмами."""
    hits: list[dict] = []
    for off in range(max_offset):
        chunk = data[off:]
        trials = [("zlib", zlib.decompress)]
        if bz2 is not None:
            trials.append(("bz2", bz2.decompress))
        if lzma is not None:
            trials.append(("lzma", lzma.decompress))
        for name, fn in trials:
            try:
                out = fn(chunk)
            except Exception:
                continue
            if len(out) > 64:
                hits.append({"algorithm": name, "offset": off, "out_size": len(out)})
    return hits


def try_simple_transforms(data: bytes, max_offset: int = 8) -> list[dict]:
    """Пробуем простейшие обфускации: XOR одним байтом, вычитание индекса и т.п."""
    n = len(data)
    variants = {
        "xor_single_byte": None,  # перебираем ниже
        "sub_index": bytes((b - i) % 256 for i, b in enumerate(data)),
        "add_index": bytes((b + i) % 256 for i, b in enumerate(data)),
        "xor_index": bytes(b ^ (i & 0xFF) for i, b in enumerate(data)),
        "delta": bytes(((data[i] - (data[i - 1] if i else 0)) % 256) for i in range(n)),
    }
    hits: list[dict] = []
    for name, variant in variants.items():
        if variant is None:
            for key in range(256):
                xored = bytes(b ^ key for b in data)
                for off in range(max_offset):
                    try:
                        out = zlib.decompress(xored[off:])
                    except Exception:
                        continue
                    if len(out) > 64:
                        hits.append({"transform": f"xor 0x{key:02x}", "offset": off, "out_size": len(out)})
            continue
        for off in range(max_offset):
            try:
                out = zlib.decompress(variant[off:])
            except Exception:
                continue
            if len(out) > 64:
                hits.append({"transform": name, "offset": off, "out_size": len(out)})
    return hits


def printable_strings(data: bytes, min_len: int = 5, limit: int = 40) -> list[str]:
    found = [m.group().decode("latin-1") for m in re.finditer(rb"[ -~]{%d,}" % min_len, data)]
    return found[:limit]


def probe(path: Path) -> dict:
    data = path.read_bytes()
    body = data[4:] if len(data) > 8 else data

    # Сигнатуру имеет смысл искать только в начале файла: внутри шифротекста
    # 2-4 байтовые совпадения встречаются случайно.
    sig_hits = {
        sig.hex(): {"label": label, "offset": 0}
        for sig, label in KNOWN_SIGNATURES.items()
        if data.startswith(sig)
    }

    counts = collections.Counter(body)
    report = {
        "file": str(path),
        "size": len(data),
        "header_hex": data[:16].hex(),
        "header_ascii": "".join(chr(b) if 32 <= b < 127 else "." for b in data[:16]),
        "signature_matches": sig_hits,
        "entropy_bits_per_byte": round(shannon_entropy(body), 4),
        "distinct_byte_values": len(counts),
        "byte_count_min": min(counts.values()),
        "byte_count_max": max(counts.values()),
        "zero_bytes": body.count(b"\x00"),
        "zero_bytes_expected_if_random": round(len(body) / 256, 1),
        "repeated_4byte_blocks": len(repeated_blocks(body, 4)),
        "repeated_3byte_blocks": len(repeated_blocks(body, 3)),
        "decompression_hits": try_decompress_offsets(data) + try_decompress_offsets(body),
        "simple_transform_hits": try_simple_transforms(body),
        "printable_strings_sample": printable_strings(data),
        "printable_chars_ratio": round(
            sum(1 for b in data if 32 <= b < 127) / len(data), 4
        ),
    }
    return report


def verdict(report: dict) -> str:
    entropy = report["entropy_bits_per_byte"]
    if report["decompression_hits"]:
        return "Полезная нагрузка РАСПАКОВЫВАЕТСЯ стандартным алгоритмом — формат можно читать/писать."
    if entropy > 7.9 and report["repeated_4byte_blocks"] == 0:
        return (
            "Полезная нагрузка выглядит как шифротекст (или шифротекст + сжатие). "
            "Простые обфускации и стандартное сжатие не сработали: формат закрыт, "
            "для записи нужен реверс алгоритма шифрования из Pro100.exe."
        )
    return "Структура неоднородная: вероятно, часть данных открыта, часть сжата. Требуется ручной разбор."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Форензик-анализ файлов PRO100 (.meb/.sto)")
    parser.add_argument("file", type=Path, help="путь к файлу .meb / .sto")
    parser.add_argument("--json", type=Path, default=None, help="сохранить отчёт в JSON")
    args = parser.parse_args(argv)

    if not args.file.exists():
        print(f"Файл не найден: {args.file}", file=sys.stderr)
        return 2

    report = probe(args.file)
    report["verdict"] = verdict(report)

    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
