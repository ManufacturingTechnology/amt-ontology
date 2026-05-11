"""
app.validation
==============
Thin wrapper around :mod:`pyshacl` for validating AMT ontologies against
their SHACL shapes (see ``shapes/``).

The motivating use case is the view files: the structural test in
``tests/test_views_bridge.py`` already catches "your view points at a URI
that does not exist in pc.ttl"-class bugs, but it open-codes the rules.
Expressing the same rules as SHACL shapes lets a reviewer state the
contract once, in declarative form, and have it enforced from CI.

API
---
* :func:`validate_graphs` is the lower-level entry point — pass any
  combination of file paths and ``rdflib.Graph`` objects to assemble the
  data graph.
* :func:`validate_view` is the common case: pass the view ``.ttl`` and its
  source ontology ``.ttl``; the default ``shapes/view-shapes.ttl`` is used.

``pyshacl`` is imported lazily so that simply importing the rest of the
``app`` package doesn't pull in a heavy dependency.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import rdflib

from .paths import SHAPES_DIR

GraphLike = Path | str | rdflib.Graph


def _coerce_to_graph(item: GraphLike) -> rdflib.Graph:
    """Return *item* as an ``rdflib.Graph``.

    Strings and :class:`pathlib.Path` are parsed as Turtle. Already-parsed
    graphs are returned unchanged.
    """
    if isinstance(item, rdflib.Graph):
        return item
    g = rdflib.Graph()
    g.parse(str(item), format="turtle")
    return g


def validate_graphs(
    data_inputs: Iterable[GraphLike],
    shapes_path: Path | str,
) -> tuple[bool, str, rdflib.Graph]:
    """Validate the union of *data_inputs* against the shapes at *shapes_path*.

    Each *data_input* may be a path to a Turtle file or an
    :class:`rdflib.Graph`. All inputs are merged into a single data graph,
    so view-side and source-side assertions are visible to the same shape
    evaluation.

    Returns ``(conforms, report_text, report_graph)``. ``conforms`` is True
    iff pyshacl found no violations; ``report_text`` is the human-readable
    report (empty when conforms is True under some pyshacl versions, but
    always safe to embed in an assertion message).
    """
    import pyshacl  # lazy import — keeps the rest of the package light

    data = rdflib.Graph()
    for item in data_inputs:
        for triple in _coerce_to_graph(item):
            data.add(triple)

    shapes = rdflib.Graph().parse(str(shapes_path), format="turtle")

    conforms, report_graph, report_text = pyshacl.validate(
        data_graph=data,
        shacl_graph=shapes,
        inference="none",
        advanced=True,
        debug=False,
    )
    return conforms, report_text, report_graph


def validate_view(
    view_path: Path | str,
    source_path: Path | str,
    shapes_path: Path | str | None = None,
) -> tuple[bool, str, rdflib.Graph]:
    """Validate a view ontology against ``shapes/view-shapes.ttl`` (default).

    *view_path* and *source_path* point at the view file and the ontology it
    is a view of (e.g. ``exhibitor_view.ttl`` + ``pc.ttl``). Both files are
    loaded into a single data graph so cross-file references resolve.
    """
    if shapes_path is None:
        shapes_path = SHAPES_DIR / "view-shapes.ttl"
    return validate_graphs([view_path, source_path], shapes_path)
