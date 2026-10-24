"""Мини-тесты без внешних зависимостей: python3 -m unittest discover -s tests"""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pro100lib.catalog import build_library  # noqa: E402
from pro100lib.geometry import box  # noqa: E402
from pro100lib.modules import MODULES, ModuleSpec, build_module  # noqa: E402


class TestGeometry(unittest.TestCase):
    def test_box_dimensions(self):
        part = box("тест", 0, 0, 0, 600, 500, 16, "ldsp_white")
        self.assertEqual(part.size, (600, 500, 16))
        self.assertEqual(len(part.faces), 6)
        for face in part.faces:
            self.assertEqual(len(face.verts), 4)
            self.assertEqual(len(face.uvs), 4)

    def test_uv_scale(self):
        part = box("тест", 0, 0, 0, 600, 300, 16, "ldsp_white")
        top = [f for f in part.faces if f.normal == (0, 0, 1)][0]
        self.assertAlmostEqual(top.uvs[1][0], 1.0)   # 600 мм = 1 повтор текстуры
        self.assertAlmostEqual(top.uvs[2][1], 0.5)   # 300 мм = 0.5 повтора


class TestModules(unittest.TestCase):
    def test_all_modules_build(self):
        for spec in MODULES:
            parts = build_module(spec)
            self.assertGreater(len(parts), 3, spec.key)
            for part in parts:
                for size in part.size:
                    self.assertGreater(size, 0, spec.key)

    def test_module_inside_bounding_box(self):
        spec = ModuleSpec("t", "тест", "Тест", 600, 720, 500, "base", shelves=2, doors=1)
        for part in build_module(spec):
            for face in part.faces:
                for x, y, z in face.verts:
                    self.assertGreaterEqual(x, -0.001)
                    self.assertLessEqual(x, spec.width + 0.001)
                    self.assertGreaterEqual(y, -18.001)  # фасад выступает вперёд
                    self.assertLessEqual(y, spec.depth + 0.001)
                    self.assertLessEqual(z, spec.height + 0.001)


class TestCatalog(unittest.TestCase):
    def test_build_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            index = build_library(out)
            self.assertEqual(len(index["modules"]), len(MODULES))
            self.assertTrue((out / "library.json").exists())
            self.assertTrue((out / "Спецификация_всех_модулей.csv").exists())

            for module in index["modules"]:
                obj = out / module["obj"]
                self.assertTrue(obj.exists(), obj)
                self.assertTrue(obj.with_suffix(".mtl").exists(), obj)
                self.assertTrue(obj.with_suffix(".csv").exists(), obj)

                nv = nvt = nvn = 0
                for line in obj.read_text(encoding="utf-8").splitlines():
                    if line.startswith("v "):
                        nv += 1
                    elif line.startswith("vt "):
                        nvt += 1
                    elif line.startswith("vn "):
                        nvn += 1
                    elif line.startswith("f "):
                        for token in line.split()[1:]:
                            a, b, c = (int(t) for t in token.split("/"))
                            self.assertTrue(1 <= a <= nv and 1 <= b <= nvt and 1 <= c <= nvn)

            with (out / "Спецификация_всех_модулей.csv").open(encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh, delimiter=";"))
            self.assertGreater(len(rows), 50)
            self.assertIn("Длина, мм", rows[0])


if __name__ == "__main__":
    unittest.main()
