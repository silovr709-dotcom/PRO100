"""Тесты библиотеки по техничке и прайсу ВИСМА: python3 -m unittest discover -s tests"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pro100lib.visma import (  # noqa: E402
    FACADE_T,
    GAP,
    build_visma_parts,
    drawer_body_height,
    facade_stack,
    module_stats,
)
from pro100lib.visma_catalog import build_visma_library  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "data" / "visma-modules.json"
PRICES = ROOT / "data" / "visma-2026-prices.json"


def _module(article: str) -> dict:
    data = json.loads(MODULES.read_text(encoding="utf-8"))
    for module in data["modules"]:
        if module["article"] == article:
            return module
    raise AssertionError(f"нет артикула {article}")


class TestFacadeStack(unittest.TestCase):
    def test_gaps_4mm(self):
        heights = facade_stack(720.0, [176, 356])
        self.assertAlmostEqual(sum(heights) + GAP * 3, 720.0, places=3)

    def test_proportions_kept(self):
        heights = facade_stack(716.0, [100, 300])
        self.assertAlmostEqual(heights[1] / heights[0], 3.0, places=2)

    def test_drawer_body_by_facade(self):
        # таблица технички п.1: фасад 180/270/360 → корпус 100/190/280 (НПВ)
        self.assertEqual(drawer_body_height(176), 100)
        self.assertEqual(drawer_body_height(270), 190)
        self.assertEqual(drawer_body_height(360), 280)


class TestVismaModules(unittest.TestCase):
    def test_known_article_sizes(self):
        module = _module("25")
        self.assertEqual(module["width"], 250)
        self.assertEqual(module["height"], 600)
        self.assertEqual(module["depth"], 300)   # навесные по техничке, п.2
        self.assertEqual(module["price"], 1900.0)

    def test_base_unit_depth_and_legs(self):
        module = _module("214")  # стол напольный 1-но дверный 150 мм
        self.assertEqual(module["kind"], "base")
        self.assertEqual(module["depth"], 500)
        parts = build_visma_parts(module)
        names = [p.name for p in parts]
        self.assertIn("опора 1", names)
        self.assertIn("цоколь ЛДСП", names)
        legs = [p for p in parts if p.name.startswith("опора")]
        self.assertEqual(len(legs), 4)
        for leg in legs:
            self.assertEqual(leg.size[2], 100.0)  # h100

    def test_back_panel_in_groove(self):
        module = _module("278")
        parts = build_visma_parts(module)
        back = [p for p in parts if p.name.startswith("задняя стенка")]
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0].size[1], 3.0)          # ХДФ 3 мм
        self.assertEqual(back[0].size[0], module["width"] - 32)  # между боковинами

    def test_sink_unit_has_no_shelf(self):
        module = _module("200")  # стол под врезную мойку
        parts = build_visma_parts(module)
        self.assertEqual(module["shelves"], 0)
        self.assertFalse([p for p in parts if p.name.startswith("полка")])

    def test_facades_within_module_height(self):
        for article in ("25", "200", "228", "278", "302"):
            module = _module(article)
            parts = build_visma_parts(module)
            facades = [p for p in parts if p.name.startswith("фасад")]
            self.assertTrue(facades, article)
            for part in facades:
                self.assertEqual(part.size[1], FACADE_T)  # МДФ 16 мм
                for face in part.faces:
                    for _x, _y, z in face.verts:
                        self.assertLessEqual(z, module["height"] + module["legs"] + 0.01, article)

    def test_every_module_builds(self):
        data = json.loads(MODULES.read_text(encoding="utf-8"))
        for module in data["modules"]:
            parts = build_visma_parts(module)
            self.assertGreater(len(parts), 3, module["article"])
            stats = module_stats(parts)
            self.assertGreater(stats["parts"], 3)
            self.assertGreaterEqual(stats["ldsp_m2"], 0)


class TestVismaCatalog(unittest.TestCase):
    def test_build_small_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            summary = build_visma_library(out, MODULES, PRICES, limit=3)
            self.assertEqual(summary["module_count"], 3)
            self.assertTrue((out / "Прайс-спецификация_ВИСМА.csv").exists())
            self.assertTrue((out / "Справочник_цен_фурнитуры.csv").exists())
            self.assertTrue((out / "Не_вошло_в_библиотеку.csv").exists())
            import csv

            with (out / "Прайс-спецификация_ВИСМА.csv").open(encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh, delimiter=";"))
            self.assertEqual(len(rows), 3)
            first = rows[0]
            self.assertEqual(first["Артикул"], "25")
            self.assertEqual(first["Цена каркаса, ₽"], "1900.0")
            self.assertGreater(float(first["Итого базовый комплект, ₽"]), 1900.0)
            # цена петли Boyard 90° = 80 ₽, 2 шт. на дверь
            self.assertEqual(first["Петли, ₽"], "160.0")

    def test_facade_prices_from_pricebook(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            summary = build_visma_library(out, MODULES, PRICES, limit=1)
            prices = summary["facade_price_per_m2"]
            self.assertEqual(prices[1], 3600.0)
            self.assertEqual(prices[4], 5200.0)


if __name__ == "__main__":
    unittest.main()
