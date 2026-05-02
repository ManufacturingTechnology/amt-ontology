"""
ontology_ui.py
==============
Flask web application for browsing and exporting the AMT product-category ontology
and its IMTS exhibitor/visitor bridge ontologies.

Startup behaviour
-----------------
- The core OWL ontology is loaded once via owlready2 and the HermiT reasoner is
  run immediately so all inferred facts are available for the lifetime of the process.
- Both bridge ontologies are loaded into independent rdflib graphs (avoiding
  owlready2 global-state collisions) and their class trees are pre-built at startup.

Routes
------
GET  /          Render the ontology browser with the core, exhibitor, and visitor tabs.
POST /          Download a CSV export of the visitor or exhibitor category hierarchy.

CLI usage
---------
    python ontology_ui.py [--host HOST] [--port PORT]
"""

import argparse
import csv
import os
from io import BytesIO, StringIO

import rdflib
from flask import Flask, render_template, request, send_file
from owlready2 import ThingClass, default_world, get_ontology, owl, sync_reasoner

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------

ONTO_PATH = "ontology/product-categories-v1.owl"
BRIDGE_EXHIBITOR_PATH = "ontology/user-bridge-imts-exhibitor.owl"
BRIDGE_VISITOR_PATH = "ontology/user-bridge-imts-visitor.owl"

# ---------------------------------------------------------------------------
# RDFlib namespace aliases (module-level constants for performance)
# ---------------------------------------------------------------------------

RDF_NS = rdflib.namespace.RDF
RDFS_NS = rdflib.namespace.RDFS
OWL_NS = rdflib.namespace.OWL

# ---------------------------------------------------------------------------
# Core ontology – loaded and reasoned over once at import time
# ---------------------------------------------------------------------------

onto = get_ontology(ONTO_PATH).load()

with onto:
    sync_reasoner(infer_property_values=True, debug=0)

# ---------------------------------------------------------------------------
# Bridge ontology loading (rdflib – independent of owlready2 global state)
# ---------------------------------------------------------------------------


def load_bridge_graph(path: str) -> rdflib.Graph:
    """
    Parse a bridge OWL file into an rdflib Graph.

    Parameters
    ----------
    path : str
        File-system path to the .owl file (RDF/XML format).

    Returns
    -------
    rdflib.Graph
        Populated graph, or an empty graph when the file does not exist.
    """
    g = rdflib.Graph()
    if os.path.exists(path):
        g.parse(path, format="xml")
    return g


BRIDGE_EXHIBITOR_GRAPH = load_bridge_graph(BRIDGE_EXHIBITOR_PATH)
BRIDGE_VISITOR_GRAPH = load_bridge_graph(BRIDGE_VISITOR_PATH)

# ---------------------------------------------------------------------------
# CSV serialisation helper
# ---------------------------------------------------------------------------


def rows_to_csv_bytes(headers: list, rows: list) -> BytesIO:
    """
    Serialise a list of rows to a UTF-8 encoded CSV wrapped in a BytesIO buffer.

    Parameters
    ----------
    headers : list
        Column header names.
    rows : list
        Iterable of row sequences (one per CSV line).

    Returns
    -------
    BytesIO
        Seeked-to-zero buffer ready to be passed to Flask's send_file.
    """
    text_io = StringIO()
    writer = csv.writer(text_io)
    writer.writerow(headers)
    writer.writerows(rows)
    bio = BytesIO(text_io.getvalue().encode("utf-8"))
    bio.seek(0)
    return bio


# ---------------------------------------------------------------------------
# owlready2 helper utilities
# ---------------------------------------------------------------------------


def get_label(cls: ThingClass) -> str:
    """Return the first rdfs:label of an owlready2 class, falling back to its name."""
    return cls.label[0] if getattr(cls, "label", None) else cls.name


def generate_category_rows(category_kind: str) -> tuple[list, list]:
    """
    Build CSV rows for a bridge ontology using the three-level hierarchy:
    Major Category → Sub Category → Product Category.

    Classification rules
    --------------------
    - **Major**: direct child of owl:Thing in the bridge ontology.
    - **Sub**:   child of a Major class that has *no* ``equivalent_to`` axiom.
    - **Product**: child of Major or Sub that carries an ``equivalent_to`` axiom
                   linking it to the core ontology, *or* any remaining leaf class.

    Parameters
    ----------
    category_kind : {'visitor', 'exhibitor'}
        Which bridge ontology to read.

    Returns
    -------
    tuple[list, list]
        ``(headers, rows)`` where *rows* is a list of three-element lists.
    """
    headers = ["Major Category", "Sub Category", "Product Category"]
    rows = []

    bridge_paths = {
        "visitor": BRIDGE_VISITOR_PATH,
        "exhibitor": BRIDGE_EXHIBITOR_PATH,
    }

    if category_kind not in bridge_paths:
        return headers, rows

    bridge_onto = get_ontology(bridge_paths[category_kind]).load()
    major_categories = [c for c in bridge_onto.classes() if owl.Thing in c.is_a]

    for major in major_categories:
        major_label = major.label.first() or major.name

        for child in major.subclasses():
            child_label = child.label.first() or child.name

            if child.equivalent_to:
                # Child is a Product directly under Major (no Sub level)
                rows.append([major_label, "", child_label])
            else:
                # Child is a Sub Category
                sub_label = child_label
                products = list(child.subclasses())

                if not products:
                    rows.append([major_label, sub_label, ""])
                else:
                    for prod in products:
                        prod_label = prod.label.first() or prod.name
                        rows.append([major_label, sub_label, prod_label])

    return headers, rows


# ---------------------------------------------------------------------------
# Core ontology tree builder (owlready2-based)
# ---------------------------------------------------------------------------


def find_root_class() -> ThingClass | None:
    """
    Resolve owl:Thing from the default world, falling back to the first class
    in the loaded ontology.

    Returns
    -------
    ThingClass or None
    """
    thing_cls = default_world["http://www.w3.org/2002/07/owl#Thing"]
    if isinstance(thing_cls, ThingClass):
        return thing_cls
    return next(iter(onto.classes()), None)


ROOT_CLASS = find_root_class()


def build_class_tree(root: ThingClass, max_depth: int = 4) -> dict | None:
    """
    Recursively build a nested dict representing the owlready2 class hierarchy.

    Parameters
    ----------
    root : ThingClass
        Starting class (typically owl:Thing).
    max_depth : int
        Maximum recursion depth; subtrees beyond this depth are returned as
        leaf nodes with no children.

    Returns
    -------
    dict or None
        ``{cls: [child_dict, ...]}`` or None when *root* is None.
    """
    if root is None:
        return None

    def recurse(cls, depth):
        if depth > max_depth:
            return {cls: []}
        return {cls: [recurse(child, depth + 1) for child in cls.subclasses()]}

    return recurse(root, 0)


def flatten_tree_for_template(tree: dict | None) -> dict | None:
    """
    Convert the raw owlready2 class tree into a JSON-serialisable dict tree
    suitable for the Jinja2 template.

    Nodes are sorted so that classes with children appear before leaves, and
    alphabetically within each group.

    Parameters
    ----------
    tree : dict or None
        Output of :func:`build_class_tree`.

    Returns
    -------
    dict or None
        ``{"label": str, "iri": str, "children": [...]}`` or None.
    """
    if tree is None:
        return None

    def convert(node):
        ((cls, children),) = node.items()
        converted_children = sorted(
            [convert(ch) for ch in children],
            key=lambda n: (0 if n["children"] else 1, n["label"].lower()),
        )
        return {
            "label": get_label(cls),
            "iri": cls.iri,
            "children": converted_children,
        }

    return convert(tree)


# ---------------------------------------------------------------------------
# Bridge ontology tree builder (rdflib-based)
# ---------------------------------------------------------------------------


def _get_rdf_label(graph: rdflib.Graph, uri: rdflib.URIRef) -> str:
    """
    Return the first ``rdfs:label`` for *uri* in *graph*, falling back to the
    URI's local name with underscores replaced by spaces.
    """
    for label in graph.objects(uri, RDFS_NS.label):
        return str(label)
    local = str(uri).split("#")[-1].split("/")[-1]
    return local.replace("_", " ")


def _find_bridge_roots(graph: rdflib.Graph) -> list:
    """
    Identify top-level classes in a bridge graph: URI-ref classes whose only
    declared superclass is ``owl:Thing`` (or that have no superclass at all).
    ``owl:Thing`` itself and blank nodes are excluded.

    Returns
    -------
    list[rdflib.URIRef]
        Alphabetically sorted list of root class URIs.
    """
    owl_thing = OWL_NS.Thing

    all_classes: set[rdflib.URIRef] = set()

    for subject in graph.subjects(RDF_NS.type, OWL_NS.Class):
        if isinstance(subject, rdflib.URIRef) and subject != owl_thing:
            all_classes.add(subject)

    for subject, _, _ in graph.triples((None, RDFS_NS.subClassOf, None)):
        if isinstance(subject, rdflib.URIRef) and subject != owl_thing:
            all_classes.add(subject)

    def is_root(cls: rdflib.URIRef) -> bool:
        return all(
            not (isinstance(parent, rdflib.URIRef) and parent != owl_thing)
            for parent in graph.objects(cls, RDFS_NS.subClassOf)
        )

    return sorted(
        [c for c in all_classes if is_root(c)],
        key=lambda c: _get_rdf_label(graph, c).lower(),
    )


def _build_bridge_subtree(
    graph: rdflib.Graph,
    cls_uri: rdflib.URIRef,
    visited: set | None = None,
) -> dict | None:
    """
    Recursively build a template-compatible node dict for one bridge class.

    Cycle protection is provided via the *visited* set.

    Parameters
    ----------
    graph : rdflib.Graph
    cls_uri : rdflib.URIRef
    visited : set, optional
        Accumulated set of already-visited URIs (mutated in place).

    Returns
    -------
    dict or None
        ``{"label", "iri", "equiv_iris", "children"}`` or None on cycle.
    """
    if visited is None:
        visited = set()
    if cls_uri in visited:
        return None
    visited.add(cls_uri)

    equiv_iris = [
        str(eq)
        for eq in graph.objects(cls_uri, OWL_NS.equivalentClass)
        if isinstance(eq, rdflib.URIRef)
    ]

    children_uris = sorted(
        [
            s
            for s in graph.subjects(RDFS_NS.subClassOf, cls_uri)
            if isinstance(s, rdflib.URIRef) and s != cls_uri
        ],
        key=lambda c: _get_rdf_label(graph, c).lower(),
    )

    children = [
        node
        for child_uri in children_uris
        if (node := _build_bridge_subtree(graph, child_uri, visited)) is not None
    ]

    # Parents before leaves, then alphabetical within each group
    children.sort(key=lambda n: (0 if n["children"] else 1, n["label"].lower()))

    return {
        "label": _get_rdf_label(graph, cls_uri),
        "iri": str(cls_uri),
        "equiv_iris": equiv_iris,
        "children": children,
    }


def build_bridge_tree(graph: rdflib.Graph) -> dict | None:
    """
    Build a virtual root node whose children are the top-level bridge classes.

    Returns a node dict compatible with the template renderer, or None when
    the graph is empty.

    Parameters
    ----------
    graph : rdflib.Graph
        A fully loaded bridge ontology graph.

    Returns
    -------
    dict or None
    """
    if len(graph) == 0:
        return None

    visited: set = set()
    children = [
        node
        for root_uri in _find_bridge_roots(graph)
        if (node := _build_bridge_subtree(graph, root_uri, visited)) is not None
    ]

    return {
        "label": "Bridge Ontology Root",
        "iri": "",
        "equiv_iris": [],
        "children": children,
    }


# Pre-build bridge trees once at startup to avoid per-request overhead
BRIDGE_EXHIBITOR_TREE = build_bridge_tree(BRIDGE_EXHIBITOR_GRAPH)
BRIDGE_VISITOR_TREE = build_bridge_tree(BRIDGE_VISITOR_GRAPH)

# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

app = Flask(__name__)

# Maps result_source form values to (category_kind, download filename)
_CSV_EXPORT_CONFIG = {
    "visitor": ("visitor", "IMTS Visitor Categories.csv"),
    "exhibitor": ("exhibitor", "IMTS Exhibitor Categories.csv"),
}


@app.route("/", methods=["GET", "POST"])
def index():
    """
    Main ontology browser endpoint.

    GET  – renders the browser with the core, exhibitor, and visitor class trees.
    POST – streams a CSV download of the selected bridge ontology's category
           hierarchy.  On error, re-renders the page with an error message.
    """
    error = None
    headers = rows = None

    # Determine the active tab from whichever source is available
    active_tab = (
        request.args.get("tab")
        or request.form.get("result_source")
        or "core"
    )

    if request.method == "POST":
        action = request.form.get("action")
        result_source = request.form.get("result_source", "")

        try:
            if action == "csv" and result_source in _CSV_EXPORT_CONFIG:
                category_kind, filename = _CSV_EXPORT_CONFIG[result_source]
                headers, rows = generate_category_rows(category_kind)
                return send_file(
                    rows_to_csv_bytes(headers, rows),
                    mimetype="text/csv",
                    as_attachment=True,
                    download_name=filename,
                )
        except Exception as exc:
            error = str(exc)

    core_tree = flatten_tree_for_template(build_class_tree(ROOT_CLASS))
    # Re-resolve active_tab from query string for GET requests (POST returns early above)
    active_tab = request.args.get("tab", active_tab)

    return render_template(
        "ontology_browser.html",
        class_tree=core_tree,
        exhibitor_tree=BRIDGE_EXHIBITOR_TREE,
        visitor_tree=BRIDGE_VISITOR_TREE,
        active_tab=active_tab,
        error=error,
        headers=headers,
        rows=rows,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AMT Ontology Browser – Flask development server."
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to listen on (default: 5000)",
    )
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=True)