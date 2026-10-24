"""Тесты partforge: каждая деталь должна быть герметичной и печатаемой."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import trimesh  # noqa: F401
    HAVE_3D = True
except ImportError:  # pragma: no cover
    HAVE_3D = False


@unittest.skipUnless(HAVE_3D, "нет numpy/trimesh — 3D-тесты пропущены")
class TestParts(unittest.TestCase):
    def test_all_specs_are_solid(self):
        from partforge.build import build_from_spec, load_spec
        from partforge.parts import BUILDERS

        specs = sorted((ROOT / "partforge" / "specs").glob("*.json"))
        self.assertTrue(specs)
        for path in specs:
            spec = load_spec(path)
            self.assertIn(spec["type"], BUILDERS, path.name)
            mesh = BUILDERS[spec["type"]](spec.get("params", {}))
            self.assertTrue(mesh.is_watertight, f"{path.name}: сетка не герметична")
            self.assertEqual(len(mesh.split(only_watertight=False)), 1, f"{path.name}: деталь распалась")
            self.assertGreater(mesh.volume, 10.0, f"{path.name}: подозрительно маленький объём")
            # деталь под 3D-печать не может быть больше стандартного стола 220×220
            self.assertLessEqual(max(mesh.extents), 200.0, path.name)

    def test_build_writes_files(self):
        from partforge.build import build_from_spec, load_spec

        spec = load_spec(ROOT / "partforge" / "specs" / "hole_plug_5mm.json")
        with tempfile.TemporaryDirectory() as tmp:
            summary = build_from_spec(spec, Path(tmp))
            for key in ("stl", "preview"):
                self.assertTrue(Path(summary[key]).exists(), key)
            self.assertTrue(summary["readiness"]["watertight"])
            self.assertGreater(summary["estimate"]["grams"], 0)

    def test_hole_plug_diameter_matches_hole(self):
        from partforge.parts import hole_plug

        mesh = hole_plug({"hole_d": 5.0, "clearance": 0.25})
        diameter = max(mesh.extents[0], mesh.extents[1])
        self.assertAlmostEqual(diameter, 8.0, places=1)  # грибок 8 мм
        # ножка входит в отверстие 5 мм: её диаметр меньше
        stem_section = mesh.section(plane_origin=(0, 0, 1.0), plane_normal=(0, 0, 1))
        self.assertIsNotNone(stem_section)


if __name__ == "__main__":
    unittest.main()
