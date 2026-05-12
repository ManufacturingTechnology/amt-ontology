"""
app.routes
==========
Flask application factory + the single ``/`` route.

Pattern
-------
:func:`create_app` is the only function callers need. It:

1. Instantiates an :class:`app.graphs.OntologyGraphs` container (optionally
   pointed at a non-default ``ontology_dir`` -- handy for tests).
2. Pre-builds the six trees, the Mermaid IM diagram, and the Cytoscape
   IM elements once, so each request just looks them up rather than
   re-parsing 500 KB of Turtle on every page load.
3. Returns a configured :class:`flask.Flask` instance.

Splitting the work this way means that importing :mod:`app` (or any of its
submodules) parses *no* ontology files. The cost is paid lazily -- either by
:meth:`OntologyGraphs.get` when a property is first read, or upfront inside
:func:`create_app`.
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, render_template, request, send_file

from .graphs import OntologyGraphs
from .im_cytoscape import generate_im_cytoscape
from .im_diagram import generate_im_mermaid
from .paths import REPO_ROOT, STATIC_DIR, TEMPLATE_DIR
from .trees import build_class_tree, build_view_tree
from .view_csv import generate_view_csv_rows, rows_to_csv_bytes

# ---------------------------------------------------------------------------
# Tab whitelist
# ---------------------------------------------------------------------------
#
# The browser groups tabs in a two-level structure:
#
#   im / im-core      - Information Model: containment tree
#   im-detail         - Information Model: Mermaid full class diagram (default)
#   im-interactive    - Information Model: Cytoscape.js movable graph
#   pc / pc-core      - Product Categories: core class taxonomy
#   pc-exhibitor      - Product Categories: Exhibitor view
#   pc-visitor        - Product Categories: Visitor view
#   ind / ind-core    - Industries: core class taxonomy
#   ind-view          - Industries: view
#
# The query-string ``tab`` value may be the long compound key (used after a
# CSV download to restore the correct sub-tab) or one of the short outer
# keys. Anything else falls back to the IM Detailed Diagram tab.

_VALID_TABS: frozenset[str] = frozenset(
    {
        "im",
        "im-core",
        "im-detail",
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
    """Build the six trees the template renders, keyed by template variable."""
    return {
        "class_tree": build_class_tree(graphs.pc, "Product Categories"),
        "industry_tree": build_class_tree(graphs.ind, "Industries"),
        "im_tree": build_class_tree(graphs.im, "Information Model", with_properties=True),
        "exhibitor_tree": build_view_tree(graphs.exhibitor, graphs.pc, "Exhibitor View"),
        "visitor_tree": build_view_tree(graphs.visitor, graphs.pc, "Visitor View"),
        "ind_view_tree": build_view_tree(graphs.ind_view, graphs.ind, "Industries View"),
    }


def create_app(ontology_dir: Path | str | None = None) -> Flask:
    """Build and return a configured Flask app.

    All heavy work (graph parsing + tree building + Mermaid generation +
    Cytoscape generation) is done eagerly here so requests stay fast.
    """
    graphs = OntologyGraphs(ontology_dir)
    trees = _build_trees(graphs)
    im_mermaid = generate_im_mermaid(graphs.im)
    im_cytoscape = generate_im_cytoscape(graphs.im)

    # CSV download routes: ``result_source`` form value -> (view, source, filename)
    csv_export_config = {
        "exhibitor": (graphs.exhibitor, graphs.pc, "IMTS Exhibitor Categories.csv"),
        "visitor": (graphs.visitor, graphs.pc, "IMTS Visitor Categories.csv"),
    }

    app = Flask(
        __name__,
        template_folder=str(TEMPLATE_DIR),
        static_folder=str(STATIC_DIR) if STATIC_DIR.exists() else None,
        root_path=str(REPO_ROOT),
    )

    @app.route("/", methods=["GET", "POST"])
    def index():
        """Render the browser, or stream a CSV download on POST."""
        error: str | None = None

        if request.method == "POST":
            action = request.form.get("action")
            result_source = request.form.get("result_source", "")
            try:
                if action == "csv" and result_source in csv_export_config:
                    view_graph, source_graph, filename = csv_export_config[result_source]
                    headers, rows = generate_view_csv_rows(view_graph, source_graph)
                    return send_file(
                        rows_to_csv_bytes(headers, rows),
                        mimetype="text/csv",
                        as_attachment=True,
                        download_name=filename,
                    )
            except Exception as exc:  # noqa: BLE001 - surface to the user
                error = str(exc)

        # Default landing tab is the IM "Detailed Diagram" sub-panel -- it's
        # the highest-information view in the browser and orients new users
        # to the model before they drill into the category trees.
        active_tab = request.args.get("tab", "im-detail")
        if active_tab not in _VALID_TABS:
            active_tab = "im-detail"

        return render_template(
            "ontology_browser.html",
            im_mermaid_source=im_mermaid,
            im_cytoscape_data=im_cytoscape,
            active_tab=active_tab,
            error=error,
            **trees,
        )

    return app
