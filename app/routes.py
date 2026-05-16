"""
app.routes
==========
Flask application factory + the single ``/`` GET route.

CSV export is library-only (no in-browser button). The browser exposes
three top-level tabs: Information Model (Core + Interactive), Product
Categories (Core + Exhibitor View + Visitor View), and Industries
(Core + View).
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, render_template, request

from .graphs import OntologyGraphs
from .im_cytoscape import generate_im_cytoscape
from .paths import REPO_ROOT, STATIC_DIR, TEMPLATE_DIR
from .trees import build_class_tree, build_classifier_tree, build_view_tree

# ---------------------------------------------------------------------------
# Tab whitelist
# ---------------------------------------------------------------------------
#
#   im / im-core      - Information Model: containment tree
#   im-interactive    - Information Model: Cytoscape.js movable graph (default)
#   pc / pc-core      - Product Categories: core class taxonomy
#   pc-exhibitor      - Product Categories: Exhibitor view
#   pc-visitor        - Product Categories: Visitor view
#   ind / ind-core    - Industries: Classification Scheme tree
#   ind-view          - Industries: view

_VALID_TABS: frozenset[str] = frozenset(
    {
        "im",
        "im-core",
        "im-interactive",
        "pc",
        "pc-core",
        "pc-exhibitor",
        "pc-visitor",
        "ind",
        "ind-core",
        "ind-view",
    }
)


def _build_trees(graphs: OntologyGraphs) -> dict:
    """Build the six trees the template renders, keyed by template variable.

    Each ontology's tree shape:

    * ``pc`` / ``im``  -- owl:Class + rdfs:subClassOf hierarchy
      (:func:`build_class_tree`).
    * ``ind``          -- OMG Commons Classifier pattern: a flat list of
      ``cmns-cls:Classifier`` individuals scoped into one
      ``cmns-cls:ClassificationScheme`` via ``cmns-cls:isDefinedIn``
      (:func:`build_classifier_tree`).
    * view files       -- ``amtmeta:Collection`` + ``amtmeta:groups`` DAG
      (:func:`build_view_tree`).
    """
    return {
        "class_tree": build_class_tree(graphs.pc, "Product Categories"),
        "industry_tree": build_classifier_tree(graphs.ind, "Industries"),
        "im_tree": build_class_tree(graphs.im, "Information Model", with_properties=True),
        "exhibitor_tree": build_view_tree(graphs.exhibitor, graphs.pc, "Exhibitor View"),
        "visitor_tree": build_view_tree(graphs.visitor, graphs.pc, "Visitor View"),
        "ind_view_tree": build_view_tree(graphs.ind_view, graphs.ind, "Industries View"),
    }


def create_app(ontology_dir: Path | str | None = None) -> Flask:
    """Build and return a configured Flask app.

    All heavy work (graph parsing + tree building + Cytoscape JSON
    generation) is done eagerly here so requests stay fast.
    """
    graphs = OntologyGraphs(ontology_dir)
    trees = _build_trees(graphs)
    im_cytoscape = generate_im_cytoscape(graphs.im)

    app = Flask(
        __name__,
        template_folder=str(TEMPLATE_DIR),
        static_folder=str(STATIC_DIR) if STATIC_DIR.exists() else None,
        root_path=str(REPO_ROOT),
    )

    @app.route("/", methods=["GET"])
    def index():
        """Render the browser."""
        # Default landing tab is the IM Interactive sub-panel.
        active_tab = request.args.get("tab", "im-interactive")
        if active_tab not in _VALID_TABS:
            active_tab = "im-interactive"

        return render_template(
            "ontology_browser.html",
            im_cytoscape_data=im_cytoscape,
            active_tab=active_tab,
            **trees,
        )

    return app
