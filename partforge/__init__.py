"""partforge — параметрические детали под 3D-печать (STL/3MF + проверки + превью).

Процесс: чертёж/фото → размеры в JSON-спеке → твердотельная модель (CSG) →
проверка печатаемости → STL/3MF + картинки видов.

Зависимости: numpy, trimesh, manifold3d (булевы операции), shapely (профили
с отверстиями), Pillow (превью).
"""

from .build import build_from_spec, load_spec  # noqa: F401
from .primitives import (  # noqa: F401
    box,
    cylinder,
    extrude,
    hollow_box,
    rounded_box,
    union,
    difference,
    intersection,
)
from .report import print_report, readiness  # noqa: F401

__all__ = [
    "build_from_spec",
    "load_spec",
    "box",
    "cylinder",
    "extrude",
    "hollow_box",
    "rounded_box",
    "union",
    "difference",
    "intersection",
    "readiness",
    "print_report",
]
__version__ = "0.1.0"
