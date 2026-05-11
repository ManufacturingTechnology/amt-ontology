"""
app.merge
=========
Merge every authored AMT ontology file into a single RDF/XML OWL file.

Why
---
The suite is authored as seven small Turtle files
(``ontology/{amtmeta,pc,ind,im,exhibitor_view,visitor_view,ind_view}.ttl``)
linked by ``owl:imports``. Tools that don't follow imports — Protégé in
"open this one file" mode, simple offline viewers, archival snapshots —
want one self-contained ontology. This module produces that file.

Output
------
``dist/amt-ontology.owl`` (RDF/XML), declaring exactly one ``owl:Ontology``
at IRI ``http://ontology.amt.org/amt-ontology``. The merged file:

* contains every logical axiom from the seven source files (classes,
  properties, individuals, restrictions, labels, prefLabels, …);
* drops the per-file ``owl:Ontology`` declarations and their attached
  metadata (each source file's ``owl:imports`` / ``dcterms:title`` /
  ``amtmeta:status`` / stewardship / nextReviewDate);
* stamps one merged ``owl:Ontology`` header carrying ``rdfs:label``,
  ``owl:versionInfo`` (the highest per-file version), and an
  ``rdfs:comment`` listing the source filenames + versions for
  traceability;
* keeps external ``owl:imports`` (gufo + shacl) so a downstream OWL tool
  still resolves the upper ontologies — the merged ontology imports the
  same two external resources that any individual AMT file does.

Internal AMT cross-imports (e.g. exhibitor_view importing pc) are
removed: once everything is in one file, they are redundant.

Invocation
----------
::

    python -m app.merge [output-dir]

Defaults to ``DIST_DIR``. Called by ``make dist-owl`` (and therefore
``make dist``), and verified by ``tests/test_merge.py`` + the CI
``dist/ is up to date`` step.
"""

from __future__ import annotations

import sys
from pathlib import Path

import rdflib
from rdflib.namespace import OWL, RDF, RDFS

from .paths import DIST_DIR, ONTOLOGY_DIR

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

# Ontology IRI of the merged artefact. Distinct from any of the per-file IRIs.
MERGED_IRI = rdflib.URIRef("http://ontology.amt.org/amt-ontology")

# External upper-ontology imports preserved in the merged file.
EXTERNAL_IMPORTS: tuple[rdflib.URIRef, ...] = (
    rdflib.URIRef("http://purl.org/nemo/gufo"),
    rdflib.URIRef("http://www.w3.org/ns/shacl"),
)

# Anything under this URI prefix is considered an "AMT-internal" IRI and
# its owl:imports edges are dropped by the merge (because the imported file
# is itself being merged in).
_AMT_INTERNAL_PREFIX = "http://ontology.amt.org/"

# Default output filename.
DEFAULT_OUTPUT_NAME = "amt-ontology.owl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_amt_internal(uri) -> bool:
    """True for any IRI inside the AMT root (e.g. .../meta, .../views/...)."""
    return isinstance(uri, rdflib.URIRef) and str(uri).startswith(_AMT_INTERNAL_PREFIX)


def _bind_prefixes(g: rdflib.Graph) -> None:
    """Bind cosmetic prefixes so the serialized RDF/XML is readable."""
    g.bind("amtmeta", "http://ontology.amt.org/meta#", replace=True)
    g.bind("pc", "http://ontology.amt.org/product-categories#", replace=True)
    g.bind("ind", "http://ontology.amt.org/industries#", replace=True)
    g.bind("im", "http://ontology.amt.org/im#", replace=True)
    g.bind("gufo", "http://purl.org/nemo/gufo#", replace=True)
    g.bind("skos", "http://www.w3.org/2004/02/skos/core#", replace=True)
    g.bind("dcterms", "http://purl.org/dc/terms/", replace=True)


def _pick_merged_version(versions: list[tuple[str, str]]) -> str:
    """Choose a single merged version string from per-file ``owl:versionInfo``
    values.

    Strategy: lexicographic max of the per-file versions. With semver-shaped
    strings ("0.1.0", "0.2.3") that coincides with the highest version in
    the set, which is a reasonable claim for "the merged file is at least
    as current as the most recently-bumped input."
    """
    return max(v for _, v in versions) if versions else "0.0.0"


# ---------------------------------------------------------------------------
# Core merge
# ---------------------------------------------------------------------------


def merge_ontologies(
    out_path: Path | str,
    ontology_dir: Path | str | None = None,
) -> Path:
    """Merge every ``*.ttl`` under *ontology_dir* into a single RDF/XML file.

    The ``ontology/imports/`` subdirectory is *not* traversed — the upper
    ontologies it contains (gufo, shacl) are referenced via ``owl:imports``
    in the output rather than baked in.

    Returns the absolute :class:`Path` of the written file.
    """
    src_dir = Path(ontology_dir) if ontology_dir else ONTOLOGY_DIR
    out_path = Path(out_path)

    inputs = sorted(p for p in src_dir.glob("*.ttl"))
    if not inputs:
        raise FileNotFoundError(f"No .ttl files found in {src_dir}")

    merged = rdflib.Graph()
    _bind_prefixes(merged)

    # Track per-file versions for the synthesised merged version + provenance.
    file_versions: list[tuple[str, str]] = []

    for ttl in inputs:
        sub = rdflib.Graph().parse(ttl.as_posix(), format="turtle")

        # Capture per-file owl:Ontology IRI + version, then strip every
        # triple where the subject is that IRI.
        for onto_iri in list(sub.subjects(RDF.type, OWL.Ontology)):
            if isinstance(onto_iri, rdflib.URIRef):
                for v in sub.objects(onto_iri, OWL.versionInfo):
                    file_versions.append((ttl.stem, str(v)))
                sub.remove((onto_iri, None, None))

        for triple in sub:
            merged.add(triple)

    # Defensive sweep: drop any remaining AMT-internal owl:imports edges
    # (covers the unlikely case that an import was asserted on a non-Ontology
    # subject, which we wouldn't have removed in the per-file pass).
    for s, p, o in list(merged.triples((None, OWL.imports, None))):
        if _is_amt_internal(o):
            merged.remove((s, p, o))

    # ── Stamp the merged ontology header ─────────────────────────────────
    merged.add((MERGED_IRI, RDF.type, OWL.Ontology))
    merged.add((MERGED_IRI, RDFS.label, rdflib.Literal("AMT Ontology — Merged Distribution")))
    for imp in EXTERNAL_IMPORTS:
        merged.add((MERGED_IRI, OWL.imports, imp))

    merged_version = _pick_merged_version(file_versions)
    merged.add((MERGED_IRI, OWL.versionInfo, rdflib.Literal(merged_version)))

    if file_versions:
        provenance = "Merged from: " + "; ".join(f"{name}={v}" for name, v in sorted(file_versions))
        merged.add((MERGED_IRI, RDFS.comment, rdflib.Literal(provenance)))

    # ── Serialize ─────────────────────────────────────────────────────────
    #
    # rdflib's RDF/XML serializer does not produce byte-stable output across
    # runs: triple iteration order depends on the underlying store's hashing,
    # and blank-node IDs are freshly generated each time. The *graph* is
    # nevertheless stable (same triples, modulo bnode renaming).
    #
    # To make ``make dist-owl`` idempotent — and the CI ``git diff dist/``
    # guard meaningful — we compare against the existing file (if any) by
    # graph isomorphism and leave it untouched when the content hasn't
    # changed. Real ontology edits still produce a real byte diff.
    if out_path.exists():
        try:
            from rdflib.compare import isomorphic

            existing = rdflib.Graph().parse(out_path.as_posix(), format="xml")
            if isomorphic(existing, merged):
                return out_path.resolve()
        except Exception:
            # If the existing file is unreadable / corrupt, fall through and
            # rewrite — better to clobber a bad file than to fail silently.
            pass

    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.serialize(destination=out_path.as_posix(), format="xml")
    return out_path.resolve()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m app.merge",
        description="Merge every authored AMT TTL into one RDF/XML OWL file.",
    )
    parser.add_argument(
        "out_dir",
        nargs="?",
        default=None,
        help="Output directory (default: project DIST_DIR).",
    )
    parser.add_argument(
        "--filename",
        default=DEFAULT_OUTPUT_NAME,
        help=f"Output filename (default: {DEFAULT_OUTPUT_NAME}).",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir) if args.out_dir else DIST_DIR
    target = out_dir / args.filename
    written = merge_ontologies(target)
    print(f"wrote {written}", file=sys.stderr)


if __name__ == "__main__":
    _cli()
