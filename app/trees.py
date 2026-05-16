"""
app.trees
=========
Tree builders for the browser's tabs, plus the structural helpers the test
suite uses to validate the view files.

Three distinct tree shapes are produced:

* **Class trees** (Product Categories Core / Information Model Core tabs)
  -- walk ``rdfs:subClassOf`` from the root ``owl:Class`` declarations
  downward. See :func:`build_class_tree`.

* **Classifier trees** (Industries Core tab) -- walk
  ``cmns-cls:Classifier`` named individuals grouped under their
  ``cmns-cls:ClassificationScheme`` via ``cmns-cls:isDefinedIn``. This
  is the OMG Commons pattern adopted by ``ind.ttl`` v0.2.0 (replacing
  the previous owl:Class / rdfs:subClassOf design). See
  :func:`build_classifier_tree`.

* **View trees** (Exhibitor / Visitor / Industries View tabs) -- walk
  ``amtmeta:Collection`` named individuals connected by ``amtmeta:groups``.
  A node with an ``skos:prefLabel`` (in either the source or the view graph)
  is treated as a leaf -- its grouped children are *not* expanded. See
  :func:`build_view_tree`.
"""

from __future__ import annotations

import rdflib
from rdflib.namespace import OWL, RDF, RDFS

from .labels import get_label, has_pref_label, view_label
from .namespaces import AMTMETA_COLLECTION, AMTMETA_GROUPS
from .properties import collect_class_properties

# ---------------------------------------------------------------------------
# Class-tree helpers (rdfs:subClassOf walks)
# ---------------------------------------------------------------------------


def find_root_classes(graph: rdflib.Graph) -> list[rdflib.URIRef]:
    """Return URI classes with no class-typed parent in the same graph."""
    classes: set[rdflib.URIRef] = set()
    for s in graph.subjects(RDF.type, OWL.Class):
        if isinstance(s, rdflib.URIRef) and s != OWL.Thing:
            classes.add(s)
    for s, _, _ in graph.triples((None, RDFS.subClassOf, None)):
        if isinstance(s, rdflib.URIRef) and s != OWL.Thing:
            classes.add(s)

    def is_root(c: rdflib.URIRef) -> bool:
        for parent in graph.objects(c, RDFS.subClassOf):
            if isinstance(parent, rdflib.URIRef) and parent != OWL.Thing and parent in classes:
                return False
        return True

    return sorted(
        [c for c in classes if is_root(c)],
        key=lambda c: get_label(graph, c).lower(),
    )


def _build_class_subtree(graph, cls, visited, *, with_properties):
    if cls in visited:
        return None
    visited.add(cls)
    children_uris = sorted(
        [
            s
            for s in graph.subjects(RDFS.subClassOf, cls)
            if isinstance(s, rdflib.URIRef) and s != cls
        ],
        key=lambda c: get_label(graph, c).lower(),
    )
    children = [
        node
        for ch in children_uris
        if (node := _build_class_subtree(graph, ch, visited, with_properties=with_properties))
        is not None
    ]
    children.sort(key=lambda n: (0 if n["children"] else 1, n["label"].lower()))
    node = {
        "label": get_label(graph, cls),
        "iri": str(cls),
        "equiv_iris": [],
        "children": children,
    }
    if with_properties:
        node["properties"] = collect_class_properties(graph, cls)
    return node


def build_class_tree(
    graph: rdflib.Graph,
    root_label: str = "Root",
    *,
    with_properties: bool = False,
) -> dict | None:
    """Build a virtual-root tree covering every root class in *graph*."""
    if len(graph) == 0:
        return None
    visited: set = set()
    children = [
        node
        for r in find_root_classes(graph)
        if (node := _build_class_subtree(graph, r, visited, with_properties=with_properties))
        is not None
    ]
    if not children:
        return None
    return {
        "label": root_label,
        "iri": "",
        "equiv_iris": [],
        "children": children,
    }


# ---------------------------------------------------------------------------
# View-tree helpers (amtmeta:Collection / amtmeta:groups walks)
# ---------------------------------------------------------------------------


def find_collections(graph: rdflib.Graph) -> set[rdflib.URIRef]:
    """Every ``amtmeta:Collection`` instance asserted in *graph*."""
    return {s for s in graph.subjects(RDF.type, AMTMETA_COLLECTION) if isinstance(s, rdflib.URIRef)}


def find_top_level_collections(graph: rdflib.Graph) -> list[rdflib.URIRef]:
    """Collections that are NOT the object of any ``amtmeta:groups`` edge."""
    collections = find_collections(graph)
    grouped = {
        o for _, _, o in graph.triples((None, AMTMETA_GROUPS, None)) if isinstance(o, rdflib.URIRef)
    }
    return sorted(
        collections - grouped,
        key=lambda c: get_label(graph, c).lower(),
    )


def has_cycle(graph: rdflib.Graph) -> tuple[bool, list]:
    """Detect a cycle in the Collection-grouping DAG using DFS colouring."""
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict = {c: WHITE for c in find_collections(graph)}
    parent: dict = {}

    def dfs(node):
        color[node] = GREY
        for child in graph.objects(node, AMTMETA_GROUPS):
            if not isinstance(child, rdflib.URIRef) or child not in color:
                continue
            if color[child] == GREY:
                cycle = [child, node]
                p = parent.get(node)
                while p is not None and p != child:
                    cycle.append(p)
                    p = parent.get(p)
                return True, list(reversed(cycle))
            if color[child] == WHITE:
                parent[child] = node
                found, c = dfs(child)
                if found:
                    return True, c
        color[node] = BLACK
        return False, []

    for n in list(color):
        if color[n] == WHITE:
            found, c = dfs(n)
            if found:
                return True, c
    return False, []


def _build_view_subtree(view_graph, source_graph, node, visited):
    if node in visited:
        return None
    visited = visited | {node}
    label = view_label(view_graph, source_graph, node)
    if has_pref_label(source_graph, node) or has_pref_label(view_graph, node):
        return {
            "label": label,
            "iri": str(node),
            "equiv_iris": [str(node)],
            "children": [],
        }
    target_uris = list(view_graph.objects(node, AMTMETA_GROUPS))
    target_uris += list(source_graph.objects(node, AMTMETA_GROUPS))
    unique_uris = sorted(
        {u for u in target_uris if isinstance(u, rdflib.URIRef)},
        key=lambda u: view_label(view_graph, source_graph, u).lower(),
    )
    children = [
        n
        for u in unique_uris
        if (n := _build_view_subtree(view_graph, source_graph, u, visited)) is not None
    ]
    children.sort(key=lambda n: (0 if n["children"] else 1, n["label"].lower()))
    return {
        "label": label,
        "iri": str(node),
        "equiv_iris": [],
        "children": children,
    }


def build_view_tree(
    view_graph: rdflib.Graph,
    source_graph: rdflib.Graph,
    root_label: str = "View Root",
) -> dict | None:
    """Build a tree of top-level Collections and their nested groups."""
    if len(view_graph) == 0:
        return None
    visited: frozenset = frozenset()
    children = [
        n
        for r in find_top_level_collections(view_graph)
        if (n := _build_view_subtree(view_graph, source_graph, r, visited)) is not None
    ]
    if not children:
        return None
    return {
        "label": root_label,
        "iri": "",
        "equiv_iris": [],
        "children": children,
    }


# ---------------------------------------------------------------------------
# Classifier-tree helpers (OMG Commons cmns-cls pattern)
# ---------------------------------------------------------------------------
#
# ind.ttl v0.2.0 represents the industry taxonomy as a flat list of
# cmns-cls:Classifier named individuals, each scoped into a single
# cmns-cls:ClassificationScheme (ind:Industry) via cmns-cls:isDefinedIn.
# No owl:Class / rdfs:subClassOf is used. This builder walks that pattern
# and emits a tree shaped the same as build_class_tree so the Jinja
# render_class_node macro renders it without modification.

CMNS_CLS_NS = rdflib.Namespace("https://www.omg.org/spec/Commons/Classifiers/")
CMNS_CLS_CLASSIFICATION_SCHEME = CMNS_CLS_NS.ClassificationScheme
CMNS_CLS_CLASSIFIER = CMNS_CLS_NS.Classifier
CMNS_CLS_IS_DEFINED_IN = CMNS_CLS_NS.isDefinedIn


def _classifier_children(graph: rdflib.Graph, scheme: rdflib.URIRef) -> list[rdflib.URIRef]:
    """Return Classifier individuals scoped into *scheme* via isDefinedIn."""
    return sorted(
        [
            c
            for c in graph.subjects(CMNS_CLS_IS_DEFINED_IN, scheme)
            if isinstance(c, rdflib.URIRef) and (c, RDF.type, CMNS_CLS_CLASSIFIER) in graph
        ],
        key=lambda c: get_label(graph, c).lower(),
    )


def build_classifier_tree(
    graph: rdflib.Graph,
    root_label: str = "Root",
) -> dict | None:
    """Build a tree of cmns-cls:ClassificationScheme roots plus the
    cmns-cls:Classifier individuals scoped into each.
    """
    if len(graph) == 0:
        return None
    schemes = sorted(
        (
            s
            for s in graph.subjects(RDF.type, CMNS_CLS_CLASSIFICATION_SCHEME)
            if isinstance(s, rdflib.URIRef)
        ),
        key=lambda s: get_label(graph, s).lower(),
    )
    if not schemes:
        return None
    children: list[dict] = []
    for scheme in schemes:
        leaves = [
            {
                "label": get_label(graph, c),
                "iri": str(c),
                "equiv_iris": [],
                "children": [],
            }
            for c in _classifier_children(graph, scheme)
        ]
        children.append(
            {
                "label": get_label(graph, scheme),
                "iri": str(scheme),
                "equiv_iris": [],
                "children": leaves,
            }
        )
    return {
        "label": root_label,
        "iri": "",
        "equiv_iris": [],
        "children": children,
    }
