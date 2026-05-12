"""
app.im_cytoscape
================
Cytoscape.js *elements* generator for the Information Model interactive tab.

Where :mod:`app.im_diagram` produces a static Mermaid ``classDiagram``
string, this module produces a JSON-serialisable graph the browser hands
to Cytoscape.js. The two views are intentionally redundant: Mermaid gives
you the canonical UML notation for documentation / paste-into-docs, and
Cytoscape gives you a movable, zoomable graph for exploration.

Output shape
------------
A dict::

    {
        "nodes": [
            {"data": {"id": ..., "label": ..., "kind": ...,
                      "stereotype": ..., "attrs": [...]}},
            ...
        ],
        "edges": [
            {"data": {"id": ..., "source": ..., "target": ...,
                      "kind": ..., "label": ..., "cardinality": ...}},
            ...
        ]
    }

* ``kind`` on a node is one of ``"class"`` (IM-internal owl:Class),
  ``"individual"`` (owl:NamedIndividual), or ``"external"`` (referenced
  by an object-property range but declared outside the IM namespace).
* ``stereotype`` carries the gUFO label (``"Kind"``, ``"Role"``,
  ``"RoleMixin"``, ``"EventType"``, ``"Category"``, ...) for class
  nodes, ``"NamedIndividual"`` for individuals, and ``"external"`` for
  external boxes. Used by the browser-side stylesheet to colour and
  shape each node.
* ``attrs`` on class nodes mirrors the inline ``+name: range [card]``
  rows from the Mermaid output, kept as structured data so the browser
  can render them inside the node body.
* ``kind`` on an edge is one of ``"subClassOf"`` (UML generalisation,
  hollow triangle), ``"instanceOf"`` (UML realisation, dashed hollow
  triangle), or ``"association"`` (filled arrow, optionally cardinality
  on the target end).

The generator reuses the same helpers as :mod:`app.im_diagram` so the
two outputs stay in sync: any change to gUFO stereotype detection,
``owl:unionOf`` domain expansion, or cardinality collection is picked
up automatically.
"""

from __future__ import annotations

import rdflib
from rdflib.namespace import OWL, RDF, RDFS

from .im_diagram import _collect_cardinalities, _expand_domains, _gufo_stereotype
from .labels import local_name
from .namespaces import in_im_namespace


def generate_im_cytoscape(graph: rdflib.Graph) -> dict:
    """Return a Cytoscape.js elements dict for *graph*.

    The dict is JSON-serialisable and ready to drop straight into
    ``cy.add(elements)`` in the browser.
    """
    cards, rest_props = _collect_cardinalities(graph)

    # Datatype-property catalogue, keyed by class local name. Same shape
    # and same rules as in im_diagram.generate_im_mermaid.
    dt_uris = set(graph.subjects(RDF.type, OWL.DatatypeProperty))
    dtprops: dict = {}

    for p in dt_uris:
        ranges = list(graph.objects(p, RDFS.range))
        rng = local_name(ranges[0]) if ranges else "string"
        for d in _expand_domains(graph, p):
            if not in_im_namespace(d):
                continue
            d_l = local_name(d)
            card = cards.get((d_l, local_name(p)), "")
            dtprops.setdefault(d_l, []).append({"name": local_name(p), "range": rng, "card": card})

    for c_l, prop_uris in rest_props.items():
        for prop in prop_uris:
            if prop not in dt_uris:
                continue
            p_l = local_name(prop)
            if any(a["name"] == p_l for a in dtprops.get(c_l, [])):
                continue
            ranges = list(graph.objects(prop, RDFS.range))
            rng = local_name(ranges[0]) if ranges else "string"
            card = cards.get((c_l, p_l), "")
            dtprops.setdefault(c_l, []).append({"name": p_l, "range": rng, "card": card})

    # --- Nodes ------------------------------------------------------------
    nodes: list[dict] = []
    declared_ids: set[str] = set()

    # IM-internal owl:Class boxes.
    im_classes = sorted(
        (c for c in graph.subjects(RDF.type, OWL.Class) if in_im_namespace(c)),
        key=local_name,
    )
    for c in im_classes:
        c_l = local_name(c)
        declared_ids.add(c_l)
        nodes.append(
            {
                "data": {
                    "id": c_l,
                    "label": c_l,
                    "kind": "class",
                    "stereotype": _gufo_stereotype(graph, c) or "",
                    "attrs": sorted(dtprops.get(c_l, []), key=lambda a: a["name"]),
                }
            }
        )

    # IM-namespace named individuals.
    im_individuals = sorted(
        (i for i in graph.subjects(RDF.type, OWL.NamedIndividual) if in_im_namespace(i)),
        key=local_name,
    )
    for ind in im_individuals:
        i_l = local_name(ind)
        declared_ids.add(i_l)
        nodes.append(
            {
                "data": {
                    "id": i_l,
                    "label": i_l,
                    "kind": "individual",
                    "stereotype": "NamedIndividual",
                    "attrs": [],
                }
            }
        )

    # External classes referenced by object-property ranges.
    ext_ids: set[str] = set()
    for p in graph.subjects(RDF.type, OWL.ObjectProperty):
        for r in graph.objects(p, RDFS.range):
            if isinstance(r, rdflib.URIRef) and not in_im_namespace(r):
                ext_ids.add(local_name(r))
    for ec in sorted(ext_ids):
        if ec in declared_ids:
            continue
        declared_ids.add(ec)
        nodes.append(
            {
                "data": {
                    "id": ec,
                    "label": ec,
                    "kind": "external",
                    "stereotype": "external",
                    "attrs": [],
                }
            }
        )

    # --- Edges ------------------------------------------------------------
    edges: list[dict] = []
    edge_counter = 0

    def _add_edge(source: str, target: str, **data) -> None:
        nonlocal edge_counter
        if source not in declared_ids or target not in declared_ids:
            return
        edge_counter += 1
        edges.append(
            {
                "data": {
                    "id": f"e{edge_counter}",
                    "source": source,
                    "target": target,
                    **data,
                }
            }
        )

    # subClassOf (IM-internal only).
    sub_edges: set[tuple[str, str]] = set()
    for c, sup in graph.subject_objects(RDFS.subClassOf):
        if not in_im_namespace(c):
            continue
        if not isinstance(sup, rdflib.URIRef):
            continue
        if not in_im_namespace(sup):
            continue
        sub_edges.add((local_name(c), local_name(sup)))
    for child, parent in sorted(sub_edges):
        _add_edge(child, parent, kind="subClassOf", label="subClassOf")

    # NamedIndividual --> class (instanceOf).
    for ind in im_individuals:
        i_l = local_name(ind)
        for t in graph.objects(ind, RDF.type):
            if t == OWL.NamedIndividual:
                continue
            if not isinstance(t, rdflib.URIRef):
                continue
            if not in_im_namespace(t):
                continue
            _add_edge(i_l, local_name(t), kind="instanceOf", label="instanceOf")

    # Object-property associations.
    for p in sorted(graph.subjects(RDF.type, OWL.ObjectProperty)):
        ranges = [r for r in graph.objects(p, RDFS.range) if isinstance(r, rdflib.URIRef)]
        if not ranges:
            continue
        p_l = local_name(p)
        for d in _expand_domains(graph, p):
            if not isinstance(d, rdflib.URIRef):
                continue
            d_l = local_name(d)
            for r in ranges:
                r_l = local_name(r)
                card = cards.get((d_l, p_l), "")
                _add_edge(
                    d_l,
                    r_l,
                    kind="association",
                    label=p_l,
                    cardinality=card,
                )

    return {"nodes": nodes, "edges": edges}
