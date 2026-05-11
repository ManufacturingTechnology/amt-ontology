"""
app.labels
==========
Label resolution policy.

Three flavours of label exist in the AMT ontologies and they are not used
interchangeably:

* ``rdfs:label``      – human-readable name, present on (almost) every
  Collection, class, and property. Used as the default display label.
* ``skos:prefLabel``  – "leaf" label policy. The presence of a prefLabel on a
  pc-side entity is what marks it as a *Product Category* in the user views:
  the view tree stops descending at such nodes and the CSV exporter only
  emits leaves that carry one.
* the URI local name  – last-resort fallback when neither label is present;
  underscores are humanised to spaces.

The functions in this module encode that policy in one place so callers
(view-tree builder, class-tree builder, CSV exporter, Mermaid generator) all
agree on what a node should be called.
"""

from __future__ import annotations

import rdflib
from rdflib.namespace import RDFS, SKOS

# ---------------------------------------------------------------------------
# Simple label lookups
# ---------------------------------------------------------------------------


def get_label(graph: rdflib.Graph, uri: rdflib.URIRef) -> str:
    """Return the first ``rdfs:label`` for *uri*, or a humanised local name.

    The fallback splits on ``#`` and ``/`` and replaces underscores with
    spaces. ``OWL.Thing`` and similar built-ins therefore come back as
    ``"Thing"`` instead of a bare URI.
    """
    for label in graph.objects(uri, RDFS.label):
        return str(label)
    s = str(uri)
    return s.split("#")[-1].split("/")[-1].replace("_", " ")


def has_pref_label(graph: rdflib.Graph, uri: rdflib.URIRef) -> bool:
    """True iff *uri* carries a non-empty ``skos:prefLabel`` in *graph*."""
    if not isinstance(uri, rdflib.URIRef):
        return False
    return any(str(lit).strip() for lit in graph.objects(uri, SKOS.prefLabel))


def pref_label(graph: rdflib.Graph, uri: rdflib.URIRef) -> str | None:
    """Return the first non-empty ``skos:prefLabel`` for *uri* in *graph*,
    or ``None`` if no usable prefLabel is asserted.

    Used by :mod:`app.view_csv` to source the *Product Category* column —
    URIs without a prefLabel are silently dropped from the export.
    """
    if not isinstance(uri, rdflib.URIRef):
        return None
    for lit in graph.objects(uri, SKOS.prefLabel):
        text = str(lit).strip()
        if text:
            return text
    return None


# ---------------------------------------------------------------------------
# View-tab label resolution
# ---------------------------------------------------------------------------


def view_label(
    view_graph: rdflib.Graph,
    source_graph: rdflib.Graph,
    uri: rdflib.URIRef,
) -> str:
    """Resolve a label for *uri* as used by view tabs.

    Resolution order:

    1. ``skos:prefLabel`` in the *source* ontology (e.g. ``pc``, ``ind``)
    2. ``skos:prefLabel`` in the *view* ontology
    3. ``rdfs:label`` in the *source* ontology
    4. ``rdfs:label`` in the *view* ontology
    5. URI local-name fallback

    The source-graph entries win when both files label the same URI: a pc-side
    prefLabel like ``"Laser Technology"`` is preferred over the view's own
    ``"Laser Technology (catalog grouping)"``.
    """
    if not isinstance(uri, rdflib.URIRef):
        return str(uri)

    for g in (source_graph, view_graph):
        for lit in g.objects(uri, SKOS.prefLabel):
            text = str(lit).strip()
            if text:
                return text
    for g in (source_graph, view_graph):
        for lit in g.objects(uri, RDFS.label):
            text = str(lit).strip()
            if text:
                return text

    raw = str(uri)
    return raw.rsplit("#", 1)[-1].rsplit("/", 1)[-1] or raw


# ---------------------------------------------------------------------------
# URI utilities
# ---------------------------------------------------------------------------


def local_name(uri) -> str:
    """Return the URI's local name (everything after ``#`` or last ``/``).

    Accepts any ``rdflib.term.Node`` for convenience; non-URIs are stringified
    and returned as-is.
    """
    s = str(uri)
    return s.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
