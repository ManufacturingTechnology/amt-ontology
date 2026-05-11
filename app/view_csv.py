"""
app.view_csv
============
Export a view ontology (``exhibitor_view``, ``visitor_view``, ``ind_view``)
as a flat three-column CSV with the historical schema:

    Major Category, Sub Category, Product Category

Algorithm
---------
For each top-level (Major) Collection in the view:

* If a grouped child is itself an ``amtmeta:Collection`` (a Sub Category in
  the view), one row is emitted per pc URI it groups; the Product Category
  cell is the ``skos:prefLabel`` of that URI in the source ontology.

* Otherwise the child is treated as a direct Product Category under Major
  (Sub Category is left blank). The Product cell is again the source
  ontology's ``skos:prefLabel``.

The Product Category is always taken verbatim from the source ontology's
``skos:prefLabel`` — leaves without a prefLabel are silently dropped from
the export. This mirrors how the live browser labels view leaves, so a
leaf that does not appear in the UI does not appear in the CSV either.
"""

from __future__ import annotations

import csv
from io import BytesIO, StringIO
from pathlib import Path

import rdflib
from rdflib.namespace import RDF

from .labels import get_label, pref_label
from .namespaces import AMTMETA_COLLECTION, AMTMETA_GROUPS
from .trees import find_top_level_collections


def generate_view_csv_rows(
    view_graph: rdflib.Graph,
    source_graph: rdflib.Graph,
) -> tuple[list[str], list[list[str]]]:
    """Build the ``(headers, rows)`` pair for a view CSV export.

    *source_graph* is the ontology the view is a view of — its
    ``skos:prefLabel`` assertions provide the Product Category cell.
    """
    headers = ["Major Category", "Sub Category", "Product Category"]
    rows: list[list[str]] = []

    for major in find_top_level_collections(view_graph):
        major_label = get_label(view_graph, major)

        for child in view_graph.objects(major, AMTMETA_GROUPS):
            if not isinstance(child, rdflib.URIRef):
                continue

            if (child, RDF.type, AMTMETA_COLLECTION) in view_graph:
                # ── Sub Category branch: nested view Collection ───────────
                sub_label = get_label(view_graph, child)
                products: list[str] = []
                for p in view_graph.objects(child, AMTMETA_GROUPS):
                    pl = pref_label(source_graph, p)
                    if pl:
                        products.append(pl)
                products.sort()
                for pl in products:
                    rows.append([major_label, sub_label, pl])
            else:
                # ── Direct Product under Major (no Sub) ───────────────────
                pl = pref_label(source_graph, child)
                if pl:
                    rows.append([major_label, "", pl])

    rows.sort()
    return headers, rows


def rows_to_csv_bytes(headers: list[str], rows: list[list[str]]) -> BytesIO:
    """Serialise ``(headers, rows)`` to a UTF-8 CSV :class:`BytesIO` buffer.

    Returns a buffer positioned at offset 0, ready for ``send_file``.
    """
    text_io = StringIO()
    writer = csv.writer(text_io)
    writer.writerow(headers)
    writer.writerows(rows)
    bio = BytesIO(text_io.getvalue().encode("utf-8"))
    bio.seek(0)
    return bio


# ---------------------------------------------------------------------------
# CLI entry point — regenerate dist/imts_*.csv from the current view files
# ---------------------------------------------------------------------------
#
# Invocation::
#
#     python -m app.view_csv [output-dir]
#
# When *output-dir* is omitted ``DIST_DIR`` (``./dist/`` by default) is used.
# Used by the ``make dist-csv`` target and by the CI ``dist/ is up to date`` step.

_DIST_EXPORTS = {
    "imts_exhibitor.csv": ("exhibitor", "pc"),
    "imts_visitor.csv": ("visitor", "pc"),
}


def regenerate_dist(out_dir: Path | str | None = None) -> list[Path]:
    """Regenerate the project's checked-in CSV exports.

    Returns the list of files written. Used by ``make dist-csv`` and CI.
    """
    from .graphs import OntologyGraphs
    from .paths import DIST_DIR

    out_dir = Path(out_dir) if out_dir else DIST_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    graphs = OntologyGraphs()
    written: list[Path] = []
    for filename, (view_attr, source_attr) in _DIST_EXPORTS.items():
        headers, rows = generate_view_csv_rows(
            getattr(graphs, view_attr),
            getattr(graphs, source_attr),
        )
        target = out_dir / filename
        target.write_bytes(rows_to_csv_bytes(headers, rows).getvalue())
        written.append(target)
    return written


def _cli(argv: list[str] | None = None) -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="python -m app.view_csv",
        description="Regenerate the checked-in view CSV exports.",
    )
    parser.add_argument(
        "out_dir",
        nargs="?",
        default=None,
        help="Output directory (defaults to the project's dist/ path).",
    )
    args = parser.parse_args(argv)

    written = regenerate_dist(args.out_dir)
    for p in written:
        print(f"wrote {p}", file=sys.stderr)


if __name__ == "__main__":
    _cli()
