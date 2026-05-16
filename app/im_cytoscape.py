"""
app.im_cytoscape
================
Cytoscape.js elements generator for the Information Model Interactive
sub-tab. The only IM diagram renderer in the package (the static Mermaid
generator was retired together with the Detailed Diagram sub-tab).

Output shape: a JSON-serialisable dict ready for ``cy.add(elements)``::

    {
        "nodes": [{"data": {"id", "label", "kind", "stereotype", "attrs"}}],
        "edges": [{"data": {"id", "source", "target", "kind", "label",
                            "cardinality"}}]
    }

Node ``kind`` is one of ``class``, ``individual``, ``external``. Edge
``kind`` is ``subClassOf`` (UML generalisation), ``instanceOf`` (UML
realisation), ``association`` (TBOX domain/range), or ``assertion``
(ABOX -- direct triple involving at least one NamedIndividual).
"""

from __future__ import annotations

import rdflib
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS

from .labels import local_name
from .namespaces import in_im_namespace

# --- gUFO stereotype lookup ------------------------------------------------

GUFO = rdflib.Namespace("http://purl.org/nemo/gufo#")

_GUFO_STEREOTYPES: tuple[tuple[str, rdflib.URIRef], ...] = (
    ("Kind", GUFO.Kind),
    ("SubKind", GUFO.SubKind),
    ("Role", GUFO.Role),
    ("RoleMixin", GUFO.RoleMixin),
    ("Phase", GUFO.Phase),
    ("PhaseMixin", GUFO.PhaseMixin),
    ("Mixin", GUFO.Mixin),
    ("Category", GUFO.Category),
    ("EventType", GUFO.EventType),
    ("SituationType", GUFO.SituationType),
    ("Quality", GUFO.Quality),
    ("Mode", GUFO.Mode),
    ("Relator", GUFO.Relator),
)

_ABOX_SKIP_PREDS = frozenset(
    {
        RDF.type,
        RDFS.subClassOf,
        RDFS.label,
        RDFS.comment,
        RDFS.seeAlso,
        RDFS.isDefinedBy,
        RDFS.domain,
        RDFS.range,
        OWL.disjointWith,
        OWL.equivalentClass,
        OWL.sameAs,
    }
)


def _gufo_stereotype(graph: rdflib.Graph, class_uri: rdflib.URIRef) -> str | None:
    types = set(graph.objects(class_uri, RDF.type))
    for label, uri in _GUFO_STEREOTYPES:
        if uri in types:
            return label
    return None


def _expand_domains(graph: rdflib.Graph, prop: rdflib.URIRef):
    for d in graph.objects(prop, RDFS.domain):
        if isinstance(d, rdflib.URIRef):
            yield d
            continue
        for union_list in graph.objects(d, OWL.unionOf):
            for item in Collection(graph, union_list):
                if isinstance(item, rdflib.URIRef):
                    yield item


def _collect_cardinalities(graph: rdflib.Graph) -> tuple[dict, dict]:
    cards: dict = {}
    rest_props: dict = {}
    for c in graph.subjects(RDF.type, OWL.Class):
        if not in_im_namespace(c):
            continue
        c_l = local_name(c)
        for r in graph.objects(c, RDFS.subClassOf):
            if (r, RDF.type, OWL.Restriction) not in graph:
                continue
            prop = next(graph.objects(r, OWL.onProperty), None)
            if not isinstance(prop, rdflib.URIRef):
                continue
            rest_props.setdefault(c_l, set()).add(prop)
            ex = next(graph.objects(r, OWL.cardinality), None)
            mn = next(graph.objects(r, OWL.minCardinality), None)
            mx = next(graph.objects(r, OWL.maxCardinality), None)
            if ex is not None:
                card = str(int(ex))
            elif mn is not None and mx is not None:
                card = f"{int(mn)}..{int(mx)}"
            elif mn is not None:
                card = f"{int(mn)}..*"
            elif mx is not None:
                card = f"0..{int(mx)}"
            else:
                continue
            cards[(c_l, local_name(prop))] = card
    return cards, rest_props


# --- Cytoscape elements generator -----------------------------------------


def generate_im_cytoscape(graph: rdflib.Graph) -> dict:
    cards, rest_props = _collect_cardinalities(graph)

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

    nodes: list[dict] = []
    declared_ids: set[str] = set()

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

    edges: list[dict] = []
    edge_counter = 0
    emitted_keys: set = set()

    def _add_edge(source: str, target: str, **data) -> None:
        nonlocal edge_counter
        if source not in declared_ids or target not in declared_ids:
            return
        key = (source, target, data.get("label", ""), data.get("kind", ""))
        if key in emitted_keys:
            return
        emitted_keys.add(key)
        edge_counter += 1
        edges.append(
            {"data": {"id": f"e{edge_counter}", "source": source, "target": target, **data}}
        )

    sub_edges: set = set()
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
                _add_edge(d_l, r_l, kind="association", label=p_l, cardinality=card)

    ind_uris = set(im_individuals)
    for s, pred, o in graph:
        if not isinstance(s, rdflib.URIRef) or not isinstance(o, rdflib.URIRef):
            continue
        if pred in _ABOX_SKIP_PREDS:
            continue
        if s not in ind_uris and o not in ind_uris:
            continue
        s_l, o_l = local_name(s), local_name(o)
        if s_l not in declared_ids or o_l not in declared_ids:
            continue
        _add_edge(s_l, o_l, kind="assertion", label=local_name(pred))

    return {"nodes": nodes, "edges": edges}
