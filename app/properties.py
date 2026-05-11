"""
app.properties
==============
Per-class property + cardinality collector for the Information Model tab.

The Information Model (``im.ttl``) attaches properties to classes via two
complementary RDF patterns:

1. an ``owl:Restriction`` on the class (``rdfs:subClassOf`` a blank node with
   ``owl:onProperty`` + cardinality keywords) — this is what supplies the
   "1..*" / "0..1" annotations next to each property in the UI;
2. an ``rdfs:domain`` on the property pointing at the class — used when a
   property applies to the class but no cardinality is pinned.

Both are merged here (deduplicated by property URI) so the template gets a
single sorted list per class. Restrictions win on cardinality; ``rdfs:domain``
properties show up with an empty cardinality column.
"""

from __future__ import annotations

import rdflib
from rdflib.namespace import OWL, RDFS

from .labels import get_label

# ---------------------------------------------------------------------------
# Cardinality formatting
# ---------------------------------------------------------------------------


def format_cardinality(graph: rdflib.Graph, restriction: rdflib.term.Node) -> str:
    """Render an ``owl:Restriction``'s cardinality as a ``min..max`` string.

    Falls back to ``"*"`` when the restriction declares no cardinality
    keywords at all (e.g. an ``owl:someValuesFrom`` restriction).
    """
    exact = next(graph.objects(restriction, OWL.cardinality), None)
    if exact is not None:
        return f"{exact}..{exact}"
    cmin = next(graph.objects(restriction, OWL.minCardinality), None)
    cmax = next(graph.objects(restriction, OWL.maxCardinality), None)
    if cmin is not None and cmax is not None:
        return f"{cmin}..{cmax}"
    if cmin is not None:
        return f"{cmin}..*"
    if cmax is not None:
        return f"0..{cmax}"
    return "*"


# ---------------------------------------------------------------------------
# Per-class property collection
# ---------------------------------------------------------------------------


def collect_class_properties(graph: rdflib.Graph, cls: rdflib.URIRef) -> list[dict]:
    """Collect properties applicable to *cls* in *graph*.

    Two sources are merged (deduplicated by property URI):

    1. ``owl:Restriction`` nodes attached via ``rdfs:subClassOf`` — produces
       a cardinality string.
    2. Properties whose ``rdfs:domain`` is *cls* — surfaced even when no
       restriction pins the cardinality.

    Each returned entry is a dict ``{"label", "card", "range", "iri"}``,
    ready for the Jinja template.
    """
    seen: set = set()
    out: list[dict] = []

    # ── (1) Restrictions on this class ─────────────────────────────────────
    for restriction in graph.objects(cls, RDFS.subClassOf):
        if isinstance(restriction, rdflib.URIRef):
            continue  # plain superclass, not a restriction
        on_prop = next(graph.objects(restriction, OWL.onProperty), None)
        if on_prop is None or on_prop in seen:
            continue
        seen.add(on_prop)
        rng = next(graph.objects(on_prop, RDFS.range), None)
        rng_label = get_label(graph, rng) if isinstance(rng, rdflib.URIRef) else ""
        out.append(
            {
                "label": get_label(graph, on_prop),
                "card": format_cardinality(graph, restriction),
                "range": rng_label,
                "iri": str(on_prop),
            }
        )

    # ── (2) rdfs:domain properties not already covered by a restriction ────
    for prop in graph.subjects(RDFS.domain, cls):
        if prop in seen or not isinstance(prop, rdflib.URIRef):
            continue
        seen.add(prop)
        rng = next(graph.objects(prop, RDFS.range), None)
        rng_label = get_label(graph, rng) if isinstance(rng, rdflib.URIRef) else ""
        out.append(
            {
                "label": get_label(graph, prop),
                "card": "",
                "range": rng_label,
                "iri": str(prop),
            }
        )

    out.sort(key=lambda p: p["label"].lower())
    return out
