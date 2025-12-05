from flask import Flask, request, render_template, send_file
from io import StringIO, BytesIO
import csv, os
from owlready2 import (
    get_ontology,
    default_world,
    sync_reasoner,
    ThingClass,
    Restriction,
)
from pyshacl import validate
import rdflib


ONTO_PATH = "ontology/amt-ontology.owl"
SHAPES_PATH = "shacl/amt-shapes.ttl"

DEFAULT_SPARQL_NS = """
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX amt:  <http://amt.org/ontology#>
"""

DEFAULT_SPARQL = """
SELECT DISTINCT ?Product_Category
WHERE {
  ?cls a owl:Class ;
       rdfs:subClassOf ?r ;
       rdfs:label ?Product_Category .

  ?r a owl:Restriction ;
     owl:onProperty amt:hasIMTSExhibitorRegistrationUser ;
     owl:someValuesFrom amt:User_Controls .
}
ORDER BY ?Product_Category"""


# -----------------------------
# Load ontology and run reasoner ONCE
# -----------------------------
onto = get_ontology(ONTO_PATH).load()

with onto:
    sync_reasoner(
        infer_property_values=True,
        debug=0
    )

INFERRED_GRAPH = default_world.as_rdflib_graph()

# -----------------------------
# Load SHACL shapes if present
# -----------------------------
shapes_graph = None
if os.path.exists(SHAPES_PATH):
    shapes_graph = rdflib.Graph()
    shapes_graph.parse(SHAPES_PATH, format="turtle")


def run_shacl():
    if shapes_graph is None:
        return None, "No SHACL shapes file found; skipping validation."

    conforms, report_graph, report_text = validate(
        data_graph=INFERRED_GRAPH,
        shacl_graph=shapes_graph,
        inference="rdfs",
        debug=False,
    )
    msg = "SHACL validation passed." if conforms \
          else "SHACL validation FAILED. Results may violate shapes."
    return conforms, msg


def run_sparql(sparql: str):
    qres = INFERRED_GRAPH.query(sparql)
    headers = [str(v) for v in qres.vars]
    rows = [[str(row[v]) if row[v] is not None else "" for v in qres.vars]
            for row in qres]
    return headers, rows


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


# -----------------------------
# Ontology helper utilities
# -----------------------------
def get_label(cls: ThingClass) -> str:
    return cls.label[0] if getattr(cls, "label", None) else cls.name


def collect_user_subclasses():
    """All subclasses under User (excluding User itself)."""
    User = next(
        (c for c in onto.classes()
         if getattr(c, "label", None) and any(lbl == "User" for lbl in c.label)),
        None,
    )
    if not User:
        return []

    collected = []

    def recurse(c):
        for sub in c.subclasses():
            collected.append(sub)
            recurse(sub)

    recurse(User)
    return collected


USER_SUBCLASSES = collect_user_subclasses()


def generate_category_rows(kind: str):
    """
    kind: 'visitor' or 'exhibitor'
    Returns (headers, rows) for the 3-column table:
    Major Category, Sub Category, Product Category
    """
    if kind == "visitor":
        if not hasattr(onto, "hasIMTSVisitorRegistrationUser"):
            raise RuntimeError("hasIMTSVisitorRegistrationUser not found in ontology")
        prop = onto.hasIMTSVisitorRegistrationUser
    elif kind == "exhibitor":
        if not hasattr(onto, "hasIMTSExhibitorRegistrationUser"):
            raise RuntimeError("hasIMTSExhibitorRegistrationUser not found in ontology")
        prop = onto.hasIMTSExhibitorRegistrationUser
    else:
        raise ValueError("kind must be 'visitor' or 'exhibitor'")

    # 1. Build mapping: User-subclass -> (Major, Sub)
    cat_for_user = {}

    for ucls in USER_SUBCLASSES:
        name = get_label(ucls)
        if " > " in name:
            major, sub = name.split(" > ", 1)
        else:
            major, sub = name, ""
        major = major.strip()
        sub = sub.strip()
        cat_for_user[ucls] = (major, sub)

    # 2. For each ontology class, check subclass-of restriction on prop
    rows = []
    seen = set()

    for cls in onto.classes():
        product_label = get_label(cls)

        for ax in cls.is_a:
            if isinstance(ax, Restriction) and ax.property is prop:
                filler = ax.value
                if isinstance(filler, ThingClass) and filler in cat_for_user:
                    major, sub = cat_for_user[filler]
                    key = (major, sub, product_label)
                    if key not in seen:
                        seen.add(key)
                        rows.append([major, sub, product_label])

    headers = ["Major Category", "Sub Category", "Product Category"]
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    return headers, rows


# -----------------------------
# Ontology browser helpers
# -----------------------------
def find_root_class():
    # Use imported owl:Thing as the global root
    thing_iri = "http://www.w3.org/2002/07/owl#Thing"
    thing_cls = default_world[thing_iri]
    if isinstance(thing_cls, ThingClass):
        return thing_cls

    # Fallback: any class in the ontology
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
                0 if n["children"] else 1,   # parents first
                n["label"].lower(),          # then alphabetical
            )
        )
        return {
            "label": get_label(cls),
            "iri": cls.iri,
            "children": converted_children,
        }

    return conv(tree)


# -----------------------------
# Flask app and template
# -----------------------------
app = Flask(__name__)

# -----------------------------
# Flask route
# -----------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    headers = rows = None

    if request.method == "POST":
        sparql = request.form.get("sparql", DEFAULT_SPARQL)
    else:
        sparql = DEFAULT_SPARQL  

    category_kind = request.form.get("category_kind", "exhibitor")
    result_source = request.form.get("result_source", "")
    shacl_msg = None

    if request.method == "POST":
        action = request.form.get("action")
        try:
            _, shacl_msg = run_shacl()

            if action == "run":
                headers, rows = run_sparql(DEFAULT_SPARQL_NS + sparql)
                result_source = "sparql"

            elif action == "generate":
                headers, rows = generate_category_rows(category_kind)
                result_source = category_kind

            elif action == "csv":
                if result_source == "sparql":
                    headers, rows = run_sparql(DEFAULT_SPARQL_NS + sparql)
                    filename = "Custom Query results.csv"
                elif result_source == "visitor":
                    headers, rows = generate_category_rows("visitor")
                    filename = "IMTS Visitor Categories.csv"
                elif result_source == "exhibitor":
                    headers, rows = generate_category_rows("exhibitor")
                    filename = "IMTS Exhibitor Categories.csv"
                else:
                    headers, rows = [], []
                    filename = "results.csv"

                sio = rows_to_csv_bytes(headers, rows)
                return send_file(
                    sio,
                    mimetype="text/csv",
                    as_attachment=True,
                    download_name=filename,
                )

        except Exception as e:
            error = str(e)

    # Build ontology browser tree
    tree = flatten_tree_for_template(build_class_tree(ROOT_CLASS))

    return render_template(
        "index.html",
        sparql=sparql,
        error=error,
        headers=headers,
        rows=rows,
        shacl_msg=shacl_msg,
        category_kind=category_kind,
        result_source=result_source,
        class_tree=tree,
    )

@app.route("/ontology", methods=["GET"])
def ontology():
    # Build ontology browser tree
    tree = flatten_tree_for_template(build_class_tree(ROOT_CLASS))

    # you can pass a minimal context here
    return render_template(
        "ontology_browser.html",
        class_tree=tree,
    )


if __name__ == "__main__":
    app.run(host="192.168.0.186", port=5000, debug=True)
