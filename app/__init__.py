"""
app
===
The AMT ontology browser package.

Modules:

* :mod:`app.paths`       -- absolute filesystem paths (CWD-independent)
* :mod:`app.namespaces`  -- RDF namespaces / common URIs
* :mod:`app.labels`      -- ``rdfs:label`` / ``skos:prefLabel`` resolution
* :mod:`app.graphs`      -- ``rdflib`` graph loader + lazy graph container
* :mod:`app.properties`  -- per-class property / cardinality collector
* :mod:`app.trees`       -- class-tree and view-tree builders + cycle detection
* :mod:`app.im_cytoscape` -- Cytoscape.js elements generator for the IM
* :mod:`app.view_csv`    -- ``(Major, Sub, Product Category)`` CSV exporter
* :mod:`app.validation`  -- ``pyshacl`` wrapper for shape validation
* :mod:`app.routes`      -- Flask ``create_app`` factory

Importing :mod:`app` itself is intentionally cheap -- nothing is pulled in
eagerly here, so ``python -m app.view_csv`` runs the submodule as
``__main__`` rather than triggering a duplicate-import RuntimeWarning.

Callers import what they actually need:

    from app.routes import create_app
    from app.trees  import find_collections, has_cycle
    from app.graphs import load_graph, OntologyGraphs
"""

__all__: list[str] = []
