from flask import Flask, request, render_template, send_file
from io import StringIO, BytesIO
import csv, os
from owlready2 import (
    get_ontology,
    default_world,
    sync_reasoner,
    ThingClass,
    owl
)
import rdflib
import argparse


ONTO_PATH = "ontology/product-categories-v1.owl"
BRIDGE_EXHIBITOR_PATH = "ontology/user-bridge-imts-exhibitor.owl"
BRIDGE_VISITOR_PATH = "ontology/user-bridge-imts-visitor.owl"

# -----------------------------
# Load ontology and run reasoner ONCE
# -----------------------------
onto = get_ontology(ONTO_PATH).load()

with onto:
    sync_reasoner(
        infer_property_values=True,
        debug=0
    )

# -----------------------------
# Load bridge ontologies with rdflib (independent of owlready2)
# -----------------------------
def load_bridge_graph(path: str) -> rdflib.Graph:
    """Load a bridge OWL ontology into an rdflib graph, returns empty graph if not found."""
    g = rdflib.Graph()
    if os.path.exists(path):
        g.parse(path, format="xml")
    return g


BRIDGE_EXHIBITOR_GRAPH = load_bridge_graph(BRIDGE_EXHIBITOR_PATH)
BRIDGE_VISITOR_GRAPH = load_bridge_graph(BRIDGE_VISITOR_PATH)

# -----------------------------
# Ontology helper utilities
# -----------------------------

def rows_to_csv_bytes(headers, rows):
    text_io = StringIO()
    w = csv.writer(text_io)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    data = text_io.getvalue().encode("utf-8")
    bio = BytesIO(data)
    bio.seek(0)
    return bio

def get_label(cls: ThingClass) -> str:
    return cls.label[0] if getattr(cls, "label", None) else cls.name


def generate_category_rows(category_kind):
    """
    Generates CSV rows for Owlready2 ontology objects.
    Logic:
    - Major: Parent is owl.Thing.
    - Sub: Child of Major, has NO equivalent_to.
    - Product: Child of Major or Sub, HAS equivalent_to.
    """
    headers = ["Major Category", "Sub Category", "Product Category"]
    rows = []

    if category_kind == "visitor":
        bridge_onto = get_ontology(BRIDGE_VISITOR_PATH).load()
    elif category_kind == "exhibitor":
        bridge_onto = get_ontology(BRIDGE_EXHIBITOR_PATH).load()
    else:
        return headers, rows
    
    major_categories = [c for c in bridge_onto.classes() if owl.Thing in c.is_a]

    for major in major_categories:
        major_label = major.label.first() or major.name
        
        for child in major.subclasses():
            child_label = child.label.first() or child.name
            
            if child.equivalent_to:
                rows.append([major_label, "", child_label])
            else:
                sub_label = child_label
                
                products = list(child.subclasses())
                if not products:
                    rows.append([major_label, sub_label, ""])
                else:
                    for prod in products:
                        prod_label = prod.label.first() or prod.name
                        # Verify it has an equivalent class[cite: 1]
                        if prod.equivalent_to:
                            rows.append([major_label, sub_label, prod_label])
                        else:
                            # If no equivalent class, it's just another sub-tier
                            # per your rules, we can skip or list as a leaf
                            rows.append([major_label, sub_label, prod_label])

    return headers, rows


# -----------------------------
# Core ontology browser helpers (owlready2-based)
# -----------------------------
def find_root_class():
    thing_iri = "http://www.w3.org/2002/07/owl#Thing"
    thing_cls = default_world[thing_iri]
    if isinstance(thing_cls, ThingClass):
        return thing_cls
    return next(iter(onto.classes()), None)


ROOT_CLASS = find_root_class()


def build_class_tree(root: ThingClass, max_depth=4):
    if root is None:
        return None

    def recurse(c, depth):
        if depth > max_depth:
            return {c: []}
        children = list(c.subclasses())
        return {c: [recurse(ch, depth + 1) for ch in children]}

    return recurse(root, 0)


def flatten_tree_for_template(tree):
    if tree is None:
        return None

    def conv(node):
        ((cls, children),) = node.items()

        converted_children = [conv(ch) for ch in children]
        converted_children.sort(
            key=lambda n: (
                0 if n["children"] else 1,
                n["label"].lower(),
            )
        )
        return {
            "label": get_label(cls),
            "iri": cls.iri,
            "children": converted_children,
        }

    return conv(tree)


# -----------------------------
# Bridge ontology tree builder (rdflib-based)
# -----------------------------

RDF_NS = rdflib.namespace.RDF
RDFS_NS = rdflib.namespace.RDFS
OWL_NS = rdflib.namespace.OWL


def _get_rdf_label(graph: rdflib.Graph, uri) -> str:
    """Return rdfs:label of a URI node, or the local name as fallback."""
    for label in graph.objects(uri, RDFS_NS.label):
        return str(label)
    local = str(uri).split("#")[-1].split("/")[-1]
    return local.replace("_", " ")


def _find_bridge_roots(graph: rdflib.Graph):
    """
    Find top-level classes in the bridge ontology:
    classes whose only superclass is owl:Thing (or have no superclass in the bridge).
    Excludes owl:Thing itself and blank nodes.
    """
    owl_thing = OWL_NS.Thing

    all_classes = set()
    for s in graph.subjects(RDF_NS.type, OWL_NS.Class):
        if isinstance(s, rdflib.URIRef) and s != owl_thing:
            all_classes.add(s)
    # Also catch classes only referenced via subClassOf
    for s, p, o in graph.triples((None, RDFS_NS.subClassOf, None)):
        if isinstance(s, rdflib.URIRef) and s != owl_thing:
            all_classes.add(s)

    def is_root(cls):
        for parent in graph.objects(cls, RDFS_NS.subClassOf):
            if isinstance(parent, rdflib.URIRef) and parent != owl_thing:
                return False
        return True

    return sorted([c for c in all_classes if is_root(c)],
                  key=lambda c: _get_rdf_label(graph, c).lower())


def _build_bridge_subtree(graph: rdflib.Graph, cls_uri, visited=None):
    """Recursively build a node dict for one bridge ontology class."""
    if visited is None:
        visited = set()
    if cls_uri in visited:
        return None
    visited.add(cls_uri)

    label = _get_rdf_label(graph, cls_uri)
    iri = str(cls_uri)

    # Collect owl:equivalentClass links (to core ontology)
    equiv_iris = []
    for eq in graph.objects(cls_uri, OWL_NS.equivalentClass):
        if isinstance(eq, rdflib.URIRef):
            equiv_iris.append(str(eq))

    # Find direct children in this graph
    children_uris = sorted(
        [s for s in graph.subjects(RDFS_NS.subClassOf, cls_uri)
         if isinstance(s, rdflib.URIRef) and s != cls_uri],
        key=lambda c: _get_rdf_label(graph, c).lower()
    )

    children = []
    for child_uri in children_uris:
        child_node = _build_bridge_subtree(graph, child_uri, visited)
        if child_node is not None:
            children.append(child_node)

    # Parents before leaves, then alphabetical
    children.sort(key=lambda n: (0 if n["children"] else 1, n["label"].lower()))

    return {
        "label": label,
        "iri": iri,
        "equiv_iris": equiv_iris,
        "children": children,
    }


def build_bridge_tree(graph: rdflib.Graph):
    """
    Build a virtual root node whose children are the top-level bridge classes.
    Returns a node dict compatible with the template renderer, or None if empty.
    """
    if len(graph) == 0:
        return None

    roots = _find_bridge_roots(graph)
    children = []
    visited = set()
    for root_uri in roots:
        node = _build_bridge_subtree(graph, root_uri, visited)
        if node:
            children.append(node)

    return {
        "label": "Bridge Ontology Root",
        "iri": "",
        "equiv_iris": [],
        "children": children,
    }


# Pre-build bridge trees at startup
BRIDGE_EXHIBITOR_TREE = build_bridge_tree(BRIDGE_EXHIBITOR_GRAPH)
BRIDGE_VISITOR_TREE = build_bridge_tree(BRIDGE_VISITOR_GRAPH)


# -----------------------------
# Flask app
# -----------------------------
app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    headers = rows = None

    active_tab = request.args.get("tab") or request.form.get("result_source") or "core"
    
    if request.method == "POST":
        action = request.form.get("action")
        result_source = request.form.get("result_source", "")
        try:
            if action == "csv":
                if result_source == "visitor":
                    headers, rows = generate_category_rows("visitor")
                    filename = "IMTS Visitor Categories.csv"
                elif result_source == "exhibitor":
                    headers, rows = generate_category_rows("exhibitor")
                    filename = "IMTS Exhibitor Categories.csv"
                else:
                    headers, rows = [], []
                    filename = "nan.csv"

                sio = rows_to_csv_bytes(headers, rows)
                return send_file(
                    sio,
                    mimetype="text/csv",
                    as_attachment=True,
                    download_name=filename,
                )

        except Exception as e:
            error = str(e)

    core_tree = flatten_tree_for_template(build_class_tree(ROOT_CLASS))
    active_tab = request.args.get("tab", "core")

    return render_template(
        "ontology_browser.html",
        class_tree=core_tree,
        exhibitor_tree=BRIDGE_EXHIBITOR_TREE,
        visitor_tree=BRIDGE_VISITOR_TREE,
        active_tab=active_tab,
        headers=headers,
        rows=rows
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Flask app with custom host and port.")

    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address to bind to (default: 127.0.0.1)"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to listen on (default: 5000)"
    )

    args = parser.parse_args()

    app.run(host=args.host, port=args.port, debug=True)