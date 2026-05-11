"""
tests.test_csv_export
=====================
Functional regression guard for the CSV exporter.

The CSV streamed by the browser's **Download CSV** button (and produced by
``make dist`` / ``python -m app.view_csv``) must match the original input
CSVs under ``resources/`` byte-for-byte.

Why this matters
----------------
``resources/IMTS Exhibitor Categories.csv`` and
``resources/IMTS Visitor Categories.csv`` are the documents that *seeded*
the entire ontology effort — they predate ``exhibitor_view.ttl`` /
``visitor_view.ttl`` and were the source of truth used to author them. The
view ontologies must faithfully re-derive those same CSVs; if they don't,
either the views drifted from the source-of-truth or the CSVs need an
intentional refresh.

Failure mode
------------
On mismatch the test prints a row-level symmetric difference (rows in the
generated output that aren't in the baseline, and rows in the baseline
that aren't in the generated output) so the failing PR can see exactly
what changed. If the change is intentional, refresh the baseline:

    make dist
    cp dist/imts_exhibitor.csv 'resources/IMTS Exhibitor Categories.csv'
    cp dist/imts_visitor.csv   'resources/IMTS Visitor Categories.csv'

and commit both diffs in the same PR.
"""

from __future__ import annotations

import csv
import io
import unittest

from app.graphs import OntologyGraphs
from app.paths import REPO_ROOT
from app.view_csv import generate_view_csv_rows, rows_to_csv_bytes

RESOURCES_DIR = REPO_ROOT / "resources"


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------


def _parse_csv_bytes(data: bytes) -> list[tuple[str, ...]]:
    """Parse CSV *data* (UTF-8) into a list of row tuples. Preserves the
    header row at index 0."""
    text = data.decode("utf-8")
    return [tuple(row) for row in csv.reader(io.StringIO(text))]


def _row_level_diff(
    baseline_rows: list[tuple[str, ...]],
    generated_rows: list[tuple[str, ...]],
    *,
    limit: int = 20,
) -> str:
    """Human-readable symmetric difference, header skipped.

    Returns an empty-ish summary when the only difference is line endings
    / whitespace / row ordering — i.e. when both sets are identical but
    the byte streams aren't.
    """
    base = set(baseline_rows[1:])
    gen = set(generated_rows[1:])
    added = sorted(gen - base)
    removed = sorted(base - gen)

    parts: list[str] = []
    if added:
        parts.append(f"  rows in generated but NOT in resources baseline ({len(added)}):")
        parts.extend(f"    + {r}" for r in added[:limit])
        if len(added) > limit:
            parts.append(f"    + … and {len(added) - limit} more")
    if removed:
        parts.append(f"  rows in resources baseline but NOT in generated ({len(removed)}):")
        parts.extend(f"    - {r}" for r in removed[:limit])
        if len(removed) > limit:
            parts.append(f"    - … and {len(removed) - limit} more")
    if not parts:
        parts.append(
            "  (no row-level differences; the byte difference is in line "
            "endings, whitespace, or row ordering)"
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class _CsvBaselineMixin:
    """Shared body for the per-view baseline tests.

    Subclasses set:

    * ``VIEW``      — the stem of the view ontology (``"exhibitor_view"`` …)
    * ``SOURCE``    — the stem of the source ontology (``"pc"``)
    * ``BASELINE``  — filename under ``resources/`` to compare against
    """

    VIEW: str
    SOURCE: str
    BASELINE: str

    @classmethod
    def setUpClass(cls):  # type: ignore[override]
        graphs = OntologyGraphs()
        cls.view_g = graphs.get(cls.VIEW)
        cls.source_g = graphs.get(cls.SOURCE)

    def test_csv_matches_resources_baseline(self):
        baseline_path = RESOURCES_DIR / self.BASELINE
        self.assertTrue(
            baseline_path.exists(),
            f"missing resources baseline: {baseline_path}",
        )
        baseline_bytes = baseline_path.read_bytes()

        headers, rows = generate_view_csv_rows(self.view_g, self.source_g)
        generated_bytes = rows_to_csv_bytes(headers, rows).getvalue()

        if generated_bytes == baseline_bytes:
            return  # ✓ byte-identical

        baseline_rows = _parse_csv_bytes(baseline_bytes)
        generated_rows = _parse_csv_bytes(generated_bytes)
        diff = _row_level_diff(baseline_rows, generated_rows)
        self.fail(
            f"\nCSV export drift against {baseline_path.name}:\n"
            f"  baseline  : {len(baseline_bytes):>6,} bytes, "
            f"{len(baseline_rows) - 1} rows\n"
            f"  generated : {len(generated_bytes):>6,} bytes, "
            f"{len(generated_rows) - 1} rows\n"
            f"{diff}\n\n"
            f"If the change is intentional, refresh the baseline:\n"
            f"  make dist\n"
            f"  cp dist/imts_{self.VIEW.replace('_view', '')}.csv "
            f"'{baseline_path}'\n"
            f"… and commit both diffs in the same PR."
        )


class TestExhibitorCsvMatchesResource(_CsvBaselineMixin, unittest.TestCase):
    VIEW = "exhibitor_view"
    SOURCE = "pc"
    BASELINE = "IMTS Exhibitor Categories.csv"


class TestVisitorCsvMatchesResource(_CsvBaselineMixin, unittest.TestCase):
    VIEW = "visitor_view"
    SOURCE = "pc"
    BASELINE = "IMTS Visitor Categories.csv"


if __name__ == "__main__":
    unittest.main(verbosity=2)
