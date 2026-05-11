"""
tests.test_shacl_shapes
=======================
Run SHACL shape validation against each user-view ontology.

Each test loads the view file together with its source ontology (so
``amtmeta:groups`` targets defined in the source resolve) and validates the
union graph against ``shapes/view-shapes.ttl``. The shapes themselves are
documented in that file; see :mod:`app.validation` for the loader.

The optional ``pyshacl`` dependency is skipped gracefully if the package
isn't installed, so this file does not break a minimal-dependency check
that excludes ``pyshacl``.
"""

from __future__ import annotations

import unittest

from app.paths import ONTOLOGY_DIR, SHAPES_DIR


def _pyshacl_available() -> tuple[bool, str]:
    try:
        import pyshacl  # noqa: F401
    except ImportError:
        return False, "pyshacl not installed (pip install pyshacl)"
    return True, ""


@unittest.skipUnless(_pyshacl_available()[0], _pyshacl_available()[1])
class _ViewShapesMixin:
    """Shared validation logic for every view/source pairing.

    Subclasses set ``VIEW`` and ``SOURCE`` to the bare ontology stems
    (``"exhibitor_view"``, ``"pc"``, …); the test method loads the
    matching ``.ttl`` files and asserts conformance against the default
    ``shapes/view-shapes.ttl`` shape set.
    """

    VIEW: str
    SOURCE: str
    SHAPES_FILE: str = "view-shapes.ttl"

    def test_conforms_to_view_shapes(self):
        from app.validation import validate_view  # lazy: pyshacl import

        view_path = ONTOLOGY_DIR / f"{self.VIEW}.ttl"
        source_path = ONTOLOGY_DIR / f"{self.SOURCE}.ttl"
        shapes_path = SHAPES_DIR / self.SHAPES_FILE

        self.assertTrue(view_path.exists(), f"missing view: {view_path}")
        self.assertTrue(source_path.exists(), f"missing source: {source_path}")
        self.assertTrue(shapes_path.exists(), f"missing shapes: {shapes_path}")

        conforms, report, _ = validate_view(view_path, source_path, shapes_path)
        self.assertTrue(
            conforms,
            f"{self.VIEW} failed SHACL validation against {self.SHAPES_FILE}:\n{report}",
        )


class TestExhibitorViewShapes(_ViewShapesMixin, unittest.TestCase):
    VIEW = "exhibitor_view"
    SOURCE = "pc"


class TestVisitorViewShapes(_ViewShapesMixin, unittest.TestCase):
    VIEW = "visitor_view"
    SOURCE = "pc"


class TestIndViewShapes(_ViewShapesMixin, unittest.TestCase):
    VIEW = "ind_view"
    SOURCE = "ind"


if __name__ == "__main__":
    unittest.main(verbosity=2)
