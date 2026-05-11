"""
app.trees
=========
Tree builders for the browser's tabs, plus the structural helpers the test
suite uses to validate the view files.

Two distinct tree shapes are produced:

* **Class trees** (Core / Industries / Information Model tabs) — walk
  ``rdfs:subClassOf`` from the root ``owl:Class`` declarations downward.
  See :func:`build_class_tree`.

* **View trees** (Exhibitor / Visitor / Industries View tabs) — walk
  ``amtmeta:Collection`` named individuals connected by ``amtmeta:groups``.
  A node with an ``skos:prefLabel`` (in either the source or the view graph)
  is treated as a leaf — its grouped children are *not* expanded. See
  :func:`build_view_tree`.

The structural helpers (:func:`find_collections`,
:func:`find_top_level_collections`, :func:`has_cycle`) are exported so the
test suite can validate the view files against the same definitions the
browser uses, instead of re-implementing them.
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
    """Return URI classes with no class-typed parent in the same graph.

    Anything either explicitly typed ``owl:Class`` or appearing as a subject
    of ``rdfs:subClassOf`` counts as a class. ``owl:Thing`` is excluded so
    that direct subclasses of Thing are themselves roots.
    """
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


def _build_class_subtree(
    graph: rdflib.Graph,
    cls: rdflib.URIRef,
    visited: set,
    *,
    with_properties: bool,
) -> dict | None:
    """Depth-first traversal helper for :func:`build_class_tree`."""
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

    node: dict = {
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
    """Build a virtual-root tree covering every root class in *graph*.

    Returns a dict shaped for the Jinja template renderer, or ``None`` when
    the graph is empty / contains no URI classes.

    ``with_properties=True`` attaches a ``properties`` list to each node via
    :func:`app.properties.collect_class_properties`; used only by the
    Information Model tab.
    """
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
    """Collections that are *not* the object of any ``amtmeta:groups`` edge.

    These are the Major (top-level) categories of a view. The result is
    sorted by ``rdfs:label`` for stable display.
    """
    collections = find_collections(graph)
    grouped = {
        o for _, _, o in graph.triples((None, AMTMETA_GROUPS, None)) if isinstance(o, rdflib.URIRef)
    }
    return sorted(
        collections - grouped,
        key=lambda c: get_label(graph, c).lower(),
    )


def has_cycle(graph: rdflib.Graph) -> tuple[bool, list]:
    """Detect a cycle in the Collection-grouping DAG using DFS colouring.

    Only edges whose target is itself a Collection in *graph* are followed
    (class leaves are inherently acyclic). Returns ``(found, path)`` where
    *path* is the cycle excerpt — empty when no cycle exists.
    """
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


def _build_view_subtree(
    view_graph: rdflib.Graph,
    source_graph: rdflib.Graph,
    node: rdflib.URIRef,
    visited: frozenset,
) -> dict | None:
    """Depth-first traversal helper for :func:`build_view_tree`.

    Leaf rule: if *node* carries an ``skos:prefLabel`` in *either* graph it is
    rendered as a leaf — its ``amtmeta:groups`` children (if any) are not
    expanded. Otherwise the node's grouped children are recursed into and
    rendered as a subtree.
    """
    if node in visited:
        return None
    visited = visited | {node}

    label = view_label(view_graph, source_graph, node)

    # prefLabel anywhere → leaf, no recursion.
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
    """Build a tree of top-level Collections and their nested groups.

    *source_graph* is the ontology this view is a view of (e.g. ``pc`` for
    the exhibitor/visitor views, ``ind`` for the industries view). It
    supplies the ``skos:prefLabel`` / ``rdfs:label`` fallbacks used to
    render leaves.
    """
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
