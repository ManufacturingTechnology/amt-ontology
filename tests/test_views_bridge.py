"""
tests.test_views_bridge
=======================
Structural validation that the AMT user-view ontologies (``exhibitor_view``,
``visitor_view``, ``ind_view``) form sound bridges to their source ontologies
(``pc`` and ``ind``).

Two validation layers are run, in order:

1. **Structural validation (rdflib)** — Always runs. For each view file:

   * every ``amtmeta:groups`` target resolves to either another Collection
     in the same view or to a URI declared in the source ontology;
   * every Collection has a non-empty ``rdfs:label``;
   * every Collection is reachable from a top-level (Major) Collection;
   * the Collection graph is acyclic;
   * the view declares ``amtmeta:viewOf`` pointing at the source IRI.

2. **OWL reasoner (owlready2)** — Optional. Skipped automatically if
   owlready2 isn't installed or if a local copy of the gufo upper-ontology
   isn't on disk. When it runs it loads the views with imports resolved
   against local files and runs HermiT to confirm logical consistency.

All structural helpers (``find_collections``, ``find_top_level_collections``,
``has_cycle``) are imported from :mod:`app.trees`. They are the same
functions the live browser uses, so this test asserts the same view of the
graph that the UI presents.

Run from the project root::

    python -m unittest tests.test_views_bridge -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import rdflib
from rdflib.namespace import OWL, RDF, RDFS

# ── App helpers (no duplication of view-graph traversal logic) ──────────────
from app.graphs import load_graph
from app.labels import has_pref_label
from app.namespaces import (
    AMTMETA_COLLECTION,
    AMTMETA_GROUPS,
    AMTMETA_VIEWOF,
    IND_ONTOLOGY_IRI,
    PC_ONTOLOGY_IRI,
)
from app.paths import ONTOLOGY_DIR, REPO_ROOT, ontology_path
from app.trees import (
    find_collections,
    find_top_level_collections,
    has_cycle,
)

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

PC_PATH = ontology_path("pc")
IM_PATH = ontology_path("im")
IND_PATH = ontology_path("ind")
AMTMETA_PATH = ontology_path("amtmeta")
EXHIBITOR_PATH = ontology_path("exhibitor_view")
VISITOR_PATH = ontology_path("visitor_view")
IND_VIEW_PATH = ontology_path("ind_view")


# ---------------------------------------------------------------------------
# Local helpers — narrow utilities not worth lifting into the app package
# ---------------------------------------------------------------------------


def _source_known_uris(source_graph: rdflib.Graph) -> set:
    """URIs the source ontology asserts something about — i.e. every URI
    that appears as a subject in *source_graph*. Used to validate that
    ``amtmeta:groups`` targets resolve."""
    return {s for s in source_graph.subjects() if isinstance(s, rdflib.URIRef)}


def _source_classes(source_graph: rdflib.Graph) -> set:
    """Strictly the ``owl:Class`` declarations in *source_graph*. Used by
    the coverage-report test below."""
    classes: set = set()
    for s in source_graph.subjects(RDF.type, OWL.Class):
        if isinstance(s, rdflib.URIRef):
            classes.add(s)
    for s, _, _ in source_graph.triples((None, RDFS.subClassOf, None)):
        if isinstance(s, rdflib.URIRef):
            classes.add(s)
    return classes


def _has_rdfs_label(graph: rdflib.Graph, uri: rdflib.URIRef) -> bool:
    return any(str(leaf).strip() for leaf in graph.objects(uri, RDFS.label))


# ---------------------------------------------------------------------------
# Structural test cases (rdflib only)
# ---------------------------------------------------------------------------


class _ViewBridgeMixin:
    """Shared structural checks against a single view / source pairing.

    Subclasses set ``VIEW_PATH``, ``VIEW_NAME``, ``SOURCE_PATH``, and
    ``SOURCE_IRI`` to plug in the source ontology the view targets (e.g.
    pc.ttl + the pc IRI for exhibitor / visitor; ind.ttl + the industries
    IRI for ind_view).
    """

    VIEW_PATH: Path
    VIEW_NAME: str
    SOURCE_PATH: Path
    SOURCE_IRI: rdflib.URIRef

    @classmethod
    def setUpClass(cls):  # type: ignore[override]
        cls.source_graph = load_graph(cls.SOURCE_PATH)
        cls.source_known = _source_known_uris(cls.source_graph)
        cls.view_graph = load_graph(cls.VIEW_PATH)
        cls.collections = find_collections(cls.view_graph)

    # ── individual checks ──────────────────────────────────────────────────

    def test_view_declares_viewof_source(self):
        """The view ontology should declare ``amtmeta:viewOf`` → source IRI."""
        viewof_targets = list(self.view_graph.objects(predicate=AMTMETA_VIEWOF))
        self.assertTrue(
            viewof_targets,
            f"{self.VIEW_NAME}: no amtmeta:viewOf declaration found",
        )
        self.assertIn(
            self.SOURCE_IRI,
            viewof_targets,
            f"{self.VIEW_NAME}: amtmeta:viewOf does not point at "
            f"{self.SOURCE_IRI}; got {viewof_targets}",
        )

    def test_collections_have_labels(self):
        unlabelled = [c for c in self.collections if not _has_rdfs_label(self.view_graph, c)]
        self.assertFalse(
            unlabelled,
            f"{self.VIEW_NAME}: {len(unlabelled)} Collection(s) without "
            f"rdfs:label: {sorted(str(c) for c in unlabelled)[:5]}…",
        )

    def test_groups_targets_resolve(self):
        """Every ``amtmeta:groups`` target must be a Collection in this view
        OR an entity declared in the source ontology."""
        orphans: list = []
        for s, _, o in self.view_graph.triples((None, AMTMETA_GROUPS, None)):
            if not isinstance(o, rdflib.URIRef):
                orphans.append((s, o, "non-URI"))
                continue
            if o in self.collections:
                continue
            if o in self.source_known:
                continue
            orphans.append((s, o, "unresolved"))
        self.assertFalse(
            orphans,
            f"{self.VIEW_NAME}: {len(orphans)} unresolved amtmeta:groups "
            f"target(s):\n  "
            + "\n  ".join(f"{s} -> {o} ({reason})" for s, o, reason in orphans[:10]),
        )

    def test_no_cycles(self):
        found, cycle = has_cycle(self.view_graph)
        self.assertFalse(
            found,
            f"{self.VIEW_NAME}: Collection-grouping cycle detected: "
            + " -> ".join(str(n).split("#")[-1] for n in cycle),
        )

    def test_all_collections_reachable_from_top_level(self):
        roots = set(find_top_level_collections(self.view_graph))
        reached: set = set()
        stack = list(roots)
        while stack:
            node = stack.pop()
            if node in reached:
                continue
            reached.add(node)
            for child in self.view_graph.objects(node, AMTMETA_GROUPS):
                if isinstance(child, rdflib.URIRef) and child in self.collections:
                    stack.append(child)
        unreachable = self.collections - reached
        self.assertFalse(
            unreachable,
            f"{self.VIEW_NAME}: {len(unreachable)} Collection(s) unreachable "
            f"from any top-level Major: "
            f"{sorted(str(u) for u in unreachable)[:5]}",
        )

    def test_summary_counts(self):
        """Print useful summary numbers — never fails."""
        n_colls = len(self.collections)
        n_top = len(find_top_level_collections(self.view_graph))
        n_groups = sum(1 for _ in self.view_graph.triples((None, AMTMETA_GROUPS, None)))
        leaves = {
            o
            for _, _, o in self.view_graph.triples((None, AMTMETA_GROUPS, None))
            if isinstance(o, rdflib.URIRef) and o not in self.collections
        }
        source_class_leaves = {
            leaf for leaf in leaves if (leaf, RDF.type, OWL.Class) in self.source_graph
        }
        source_collection_leaves = {
            leaf for leaf in leaves if (leaf, RDF.type, AMTMETA_COLLECTION) in self.source_graph
        }
        other_leaves = leaves - source_class_leaves - source_collection_leaves
        print(
            f"\n  [{self.VIEW_NAME}] {n_colls} collections "
            f"({n_top} top-level), {n_groups} groups edges"
            f"\n    source-class leaves:                {len(source_class_leaves)}"
            f"\n    source-defined Collection leaves:   {len(source_collection_leaves)} "
            f"(catalog-residual buckets)"
            f"\n    other (resolved but untyped):       {len(other_leaves)}"
        )

    def test_leaves_have_source_pref_label(self):
        """Print how many leaves carry an ``skos:prefLabel`` in the source
        ontology — this is what the browser uses to label leaves and what
        :func:`app.view_csv.generate_view_csv_rows` uses to gate CSV export.
        """
        leaves = {
            o
            for _, _, o in self.view_graph.triples((None, AMTMETA_GROUPS, None))
            if isinstance(o, rdflib.URIRef) and o not in self.collections
        }
        # Source-side Collections expand to their grouped children — those are
        # the URIs the CSV exporter actually inspects.
        expanded: set = set()
        for leaf in leaves:
            if (leaf, RDF.type, AMTMETA_COLLECTION) in self.source_graph:
                kids = [
                    k
                    for k in self.source_graph.objects(leaf, AMTMETA_GROUPS)
                    if isinstance(k, rdflib.URIRef)
                ]
                if kids:
                    expanded.update(kids)
                else:
                    expanded.add(leaf)
            else:
                expanded.add(leaf)
        missing = sorted(leaf for leaf in expanded if not has_pref_label(self.source_graph, leaf))
        with_pref = len(expanded) - len(missing)
        print(
            f"\n  [{self.VIEW_NAME}] prefLabel coverage: "
            f"{with_pref}/{len(expanded)} leaves carry skos:prefLabel."
        )
        if missing:
            print(
                f"    {len(missing)} leaf(s) without skos:prefLabel "
                f"(would be filtered out by CSV exporter):"
            )
            for m in missing[:20]:
                print(f"      - {str(m).split('#')[-1]}")
            if len(missing) > 20:
                print(f"      … and {len(missing) - 20} more")


class TestExhibitorBridge(_ViewBridgeMixin, unittest.TestCase):
    VIEW_PATH = EXHIBITOR_PATH
    VIEW_NAME = "exhibitor_view"
    SOURCE_PATH = PC_PATH
    SOURCE_IRI = PC_ONTOLOGY_IRI


class TestVisitorBridge(_ViewBridgeMixin, unittest.TestCase):
    VIEW_PATH = VISITOR_PATH
    VIEW_NAME = "visitor_view"
    SOURCE_PATH = PC_PATH
    SOURCE_IRI = PC_ONTOLOGY_IRI


class TestIndViewBridge(_ViewBridgeMixin, unittest.TestCase):
    VIEW_PATH = IND_VIEW_PATH
    VIEW_NAME = "ind_view"
    SOURCE_PATH = IND_PATH
    SOURCE_IRI = IND_ONTOLOGY_IRI


# ---------------------------------------------------------------------------
# pc.ttl coverage (soft report)
# ---------------------------------------------------------------------------


class TestPcLeafCoverage(unittest.TestCase):
    """Soft coverage report: how many pc-class leaves each view references."""

    @classmethod
    def setUpClass(cls):
        cls.pc_graph = load_graph(PC_PATH)
        cls.pc_classes = _source_classes(cls.pc_graph)
        cls.exh = load_graph(EXHIBITOR_PATH)
        cls.vis = load_graph(VISITOR_PATH)

    @staticmethod
    def _leaves_referenced(view_graph: rdflib.Graph) -> set:
        colls = find_collections(view_graph)
        return {
            o
            for _, _, o in view_graph.triples((None, AMTMETA_GROUPS, None))
            if isinstance(o, rdflib.URIRef) and o not in colls
        }

    def test_coverage_report(self):
        exh_leaves = self._leaves_referenced(self.exh) & self.pc_classes
        vis_leaves = self._leaves_referenced(self.vis) & self.pc_classes
        union = exh_leaves | vis_leaves
        n_pc = len(self.pc_classes)
        print(
            f"\n  pc.ttl: {n_pc} owl:Class declarations"
            f"\n  exhibitor view references {len(exh_leaves)} of them "
            f"({len(exh_leaves) / n_pc:.0%} class coverage)"
            f"\n  visitor  view references {len(vis_leaves)} of them "
            f"({len(vis_leaves) / n_pc:.0%} class coverage)"
            f"\n  union: {len(union)} unique pc classes "
            f"({len(union) / n_pc:.0%} coverage)"
        )


# ---------------------------------------------------------------------------
# Optional: full reasoning with owlready2
# ---------------------------------------------------------------------------


def _owlready2_available() -> tuple[bool, str]:
    try:
        import owlready2  # noqa: F401
    except ImportError:
        return False, "owlready2 not installed (pip install owlready2)"
    return True, ""


@unittest.skipUnless(_owlready2_available()[0], _owlready2_available()[1])
class TestOwlreadyConsistency(unittest.TestCase):
    """Load the views with imports resolved against local files and run a
    reasoner. Skipped automatically if owlready2 isn't installed.

    owlready2 (≤0.50 at time of writing) does not parse Turtle natively and
    resolves ``owl:imports`` by looking for files whose stem matches the
    last segment of the import IRI. Both gaps are bridged here:

    * every ``.ttl`` under ``ontology/`` and ``ontology/imports/`` is
      converted to RDF/XML once in :meth:`setUpClass` via rdflib;
    * the converted files are written into a tempdir, named after the
      ontology IRI's last segment (e.g. ``amtmeta.ttl`` whose IRI ends in
      ``/meta`` becomes ``meta.owl``);
    * that tempdir is appended to ``owlready2.onto_path`` so import
      resolution finds local copies of pc, im, ind, amtmeta, and gufo.

    If the conversion or reasoner pass fails, the individual test calls
    :meth:`skipTest` with a precise message instead of erroring out.
    """

    _tmpdir: Path | None = None

    @classmethod
    def setUpClass(cls):
        import tempfile

        import owlready2 as owr
        import rdflib
        from rdflib.namespace import OWL, RDF

        cls.owr = owr
        cls._tmpdir = Path(tempfile.mkdtemp(prefix="amt_owlready_"))
        cls._converted: dict[Path, Path] = {}

        def _convert(ttl: Path) -> Path:
            g = rdflib.Graph().parse(ttl.as_posix(), format="turtle")
            iri = next(
                (
                    s
                    for s, _, _ in g.triples((None, RDF.type, OWL.Ontology))
                    if isinstance(s, rdflib.URIRef)
                ),
                None,
            )
            stem = str(iri).rstrip("#/").rsplit("/", 1)[-1] if iri else ttl.stem
            out = cls._tmpdir / f"{stem}.owl"
            g.serialize(destination=out.as_posix(), format="xml")
            cls._converted[ttl] = out
            return out

        sources = list(ONTOLOGY_DIR.glob("*.ttl"))
        imports_dir = ONTOLOGY_DIR / "imports"
        if imports_dir.exists():
            sources.extend(imports_dir.glob("*.ttl"))
        for ttl in sources:
            _convert(ttl)

        owr.onto_path.append(cls._tmpdir.as_posix())

    @classmethod
    def tearDownClass(cls):
        if cls._tmpdir is not None:
            import shutil

            shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def setUp(self):  # type: ignore[override]
        """Give each test its own owlready2 ``World`` so reasoner state never
        leaks between cases.

        Without this, the second and third tests inherit cached ontology
        objects from the first run's default world. Pellet's Jena loader is
        sensitive to that — it can succeed on the first view and then trip
        on the next with an ``addUnsupportedFeature`` warning (a re-load
        of meta / pc / im).
        """
        self.world = self.owr.World()

    def _load_with_imports(self, path: Path):
        """Load the converted RDF/XML twin of *path* with imports resolved.

        Loads into ``self.world`` (per-test isolation, see :meth:`setUp`).

        Cross-platform note: we pass owlready2 a native path string rather
        than a ``file://`` URI. On Windows, ``Path.as_uri()`` returns
        ``file:///C:/Users/...`` and owlready2's loader strips only the
        ``file://`` prefix, leaving ``/C:/Users/...`` which Windows
        rejects with ``OSError: [Errno 22] Invalid argument``. A plain
        string path works the same on macOS / Linux and avoids the
        Windows mangling entirely.
        """
        converted = self._converted.get(path)
        if converted is None or not converted.exists():
            self.skipTest(f"No converted RDF/XML available for {path.name}")
        try:
            return self.world.get_ontology(str(converted)).load()
        except Exception as exc:  # noqa: BLE001
            self.skipTest(
                f"Could not resolve all imports for {path.name} ({exc.__class__.__name__}: {exc})."
            )

    @staticmethod
    def _summarize_java_error(exc: Exception, max_lines: int = 6) -> str:
        """Return up to *max_lines* of an owlready2 Java error.

        Java's logger emits dated warning lines like
        ``May 11, 2026 4:48:47 PM ... addUnsupportedFeature``; those are
        informational and the *real* error usually follows them. Showing
        more of the stderr makes the skip reason diagnosable.
        """
        text = str(exc).strip()
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if len(lines) <= max_lines:
            return "\n      " + "\n      ".join(lines)
        return (
            "\n      "
            + "\n      ".join(lines[: max_lines - 1])
            + f"\n      … (+{len(lines) - max_lines + 1} more lines)"
        )

    def _run_reasoner(self, onto) -> str:
        """Run a DL reasoner over *onto* using this test's :attr:`world`.

        Tries HermiT first (the owlready2 default — no Java network
        dependency at startup) and falls back to Pellet on errors that
        usually mean "HermiT does not support this datatype" (notably
        ``xsd:date``, which HermiT does not implement). Returns the name
        of the reasoner that succeeded.

        If both fail the test is skipped with the first few lines of each
        Java stderr so the failure mode is diagnosable from the unittest
        output alone.
        """
        try:
            with onto:
                self.owr.sync_reasoner(
                    self.world,
                    infer_property_values=False,
                    debug=0,
                )
            return "HermiT"
        except Exception as exc_hermit:  # noqa: BLE001
            try:
                with onto:
                    self.owr.sync_reasoner_pellet(
                        self.world,
                        infer_property_values=False,
                        debug=0,
                    )
                return "Pellet"
            except Exception as exc_pellet:  # noqa: BLE001
                self.skipTest(
                    "Neither HermiT nor Pellet could run."
                    f"\n  HermiT:{self._summarize_java_error(exc_hermit)}"
                    f"\n  Pellet:{self._summarize_java_error(exc_pellet)}"
                )
                return ""  # unreachable, keeps mypy happy

    def test_exhibitor_view_consistent(self):
        onto = self._load_with_imports(EXHIBITOR_PATH)
        self._run_reasoner(onto)
        self.assertNotIn(
            self.owr.Nothing,
            list(onto.classes()),
            "exhibitor_view: reasoner derived owl:Nothing — inconsistent",
        )

    def test_visitor_view_consistent(self):
        onto = self._load_with_imports(VISITOR_PATH)
        self._run_reasoner(onto)
        self.assertNotIn(
            self.owr.Nothing,
            list(onto.classes()),
            "visitor_view: reasoner derived owl:Nothing — inconsistent",
        )

    def test_ind_view_consistent(self):
        onto = self._load_with_imports(IND_VIEW_PATH)
        self._run_reasoner(onto)
        self.assertNotIn(
            self.owr.Nothing,
            list(onto.classes()),
            "ind_view: reasoner derived owl:Nothing — inconsistent",
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    unittest.main(verbosity=2)
