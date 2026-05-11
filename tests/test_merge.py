"""
tests.test_merge
================
Sanity tests for the merged ``amt-ontology.owl`` artefact produced by
:func:`app.merge.merge_ontologies`.

Two layers of checks:

1. **Round-trip in memory** (always runs) — call the merger directly, parse
   the resulting file, and assert structural invariants: exactly one
   ``owl:Ontology`` at the expected IRI, the expected external imports,
   no leftover AMT-internal imports, and class counts that match the sum
   of class counts across the source TTLs.

2. **Committed snapshot agreement** (skipped if ``dist/amt-ontology.owl``
   isn't present) — load the checked-in snapshot and assert it is
   isomorphic to a freshly-generated merge of the current TTL state.
   This is the test the CI ``dist/ is up to date`` step relies on
   semantically; running it locally catches "I edited a TTL but forgot
   to run ``make dist-owl``" before the PR opens.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import rdflib
from rdflib.compare import isomorphic
from rdflib.namespace import OWL, RDF

from app.merge import (
    EXTERNAL_IMPORTS,
    MERGED_IRI,
    merge_ontologies,
)
from app.paths import DIST_DIR, ONTOLOGY_DIR

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classes(graph: rdflib.Graph) -> set[rdflib.URIRef]:
    return {s for s in graph.subjects(RDF.type, OWL.Class) if isinstance(s, rdflib.URIRef)}


def _source_class_total() -> int:
    """Sum of ``owl:Class`` declarations across every authored TTL."""
    total = 0
    for ttl in sorted(ONTOLOGY_DIR.glob("*.ttl")):
        g = rdflib.Graph().parse(ttl.as_posix(), format="turtle")
        total += len(_classes(g))
    return total


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestMergeStructure(unittest.TestCase):
    """Generate a fresh merge into a tempdir and check the result's shape."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = Path(tempfile.mkdtemp(prefix="amt_merge_test_"))
        cls._path = merge_ontologies(cls._tmp / "amt-ontology.owl")
        cls.graph = rdflib.Graph().parse(cls._path.as_posix(), format="xml")

    @classmethod
    def tearDownClass(cls):
        import shutil

        shutil.rmtree(cls._tmp, ignore_errors=True)

    # ── header ─────────────────────────────────────────────────────────────

    def test_exactly_one_ontology_declaration(self):
        ontos = list(self.graph.subjects(RDF.type, OWL.Ontology))
        self.assertEqual(
            ontos,
            [MERGED_IRI],
            f"expected a single owl:Ontology at {MERGED_IRI}, got {ontos}",
        )

    def test_version_info_is_present(self):
        vs = list(self.graph.objects(MERGED_IRI, OWL.versionInfo))
        self.assertEqual(
            len(vs), 1, f"merged ontology should declare one owl:versionInfo, got {vs}"
        )

    def test_external_imports_present(self):
        actual = set(self.graph.objects(MERGED_IRI, OWL.imports))
        expected = set(EXTERNAL_IMPORTS)
        self.assertEqual(
            actual,
            expected,
            "merged ontology must import exactly the external upper "
            f"ontologies: {sorted(expected)} (got {sorted(actual)})",
        )

    def test_no_internal_amt_imports(self):
        """Once everything is in one file, internal AMT cross-imports are
        redundant and must not be re-emitted."""
        leftovers = [
            o
            for _, _, o in self.graph.triples((None, OWL.imports, None))
            if isinstance(o, rdflib.URIRef) and str(o).startswith("http://ontology.amt.org/")
        ]
        self.assertFalse(
            leftovers,
            f"unexpected internal AMT imports in merged file: {leftovers}",
        )

    # ── content counts ────────────────────────────────────────────────────

    def test_class_count_matches_source_total(self):
        merged_classes = len(_classes(self.graph))
        source_total = _source_class_total()
        # The source files have no overlap today (each owl:Class is declared
        # in exactly one TTL). If that ever changes, this test correctly
        # tightens to "merged ≤ source_total".
        self.assertEqual(
            merged_classes,
            source_total,
            f"merged owl:Class count ({merged_classes}) does not match "
            f"sum across source TTLs ({source_total})",
        )


class TestMergeSnapshotAgreement(unittest.TestCase):
    """The checked-in ``dist/amt-ontology.owl`` must be isomorphic to a fresh
    merge of the current TTL state. Skips automatically if the snapshot
    isn't on disk (e.g. a brand-new clone before ``make dist`` runs)."""

    SNAPSHOT = DIST_DIR / "amt-ontology.owl"

    def test_snapshot_matches_current_ttl_state(self):
        if not self.SNAPSHOT.exists():
            self.skipTest(f"no snapshot at {self.SNAPSHOT}; run `make dist-owl` first")

        snapshot = rdflib.Graph().parse(self.SNAPSHOT.as_posix(), format="xml")

        with tempfile.TemporaryDirectory(prefix="amt_merge_check_") as tmp:
            fresh_path = merge_ontologies(Path(tmp) / "fresh.owl")
            fresh = rdflib.Graph().parse(fresh_path.as_posix(), format="xml")

        self.assertTrue(
            isomorphic(snapshot, fresh),
            f"\n{self.SNAPSHOT.name} is out of sync with the current TTL state.\n"
            f"  snapshot triples: {len(snapshot)}\n"
            f"  fresh    triples: {len(fresh)}\n"
            f"Run `make dist-owl` and commit the result in the same PR as "
            f"the ontology change.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
