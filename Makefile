# Makefile
# ─────────────────────────────────────────────────────────────────────────────
# Common project tasks. Run `make help` for the menu.
#
# All targets are PHONY — there are no file-target dependencies. The point
# of this file is discoverability, not incremental builds.

PY ?= python

.PHONY: help install serve test shacl reasoner-check lint format dist dist-csv dist-owl dist-xlsx clean

help:                  ## list available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "} {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:               ## editable install with dev + reasoner extras
	$(PY) -m pip install -e ".[dev,reasoner]"

serve:                 ## run the Flask development server
	$(PY) ontology_ui.py

test:                  ## run the full test suite
	$(PY) -m unittest discover -s tests -v

shacl:                 ## run only the SHACL validation tests
	$(PY) -m unittest tests.test_shacl_shapes -v

reasoner-check:        ## run only the owlready2 (HermiT/Pellet) reasoner tests
	$(PY) -m unittest tests.test_views_bridge.TestOwlreadyConsistency -v

lint:                  ## ruff check + format check
	ruff check .
	ruff format --check .

format:                ## apply ruff formatter
	ruff format .

dist: dist-csv dist-owl dist-xlsx  ## regenerate every artefact in dist/

dist-csv:              ## regenerate dist/imts_*.csv from the views
	$(PY) -m app.view_csv dist

dist-owl:              ## regenerate dist/amt-ontology.owl (merged RDF/XML)
	$(PY) -m app.merge dist

dist-xlsx:             ## regenerate dist/AMT Taxonomy - Product Interest Category.xlsx
	$(PY) -m app.view_xlsx dist

clean:                 ## remove caches
	rm -rf .pytest_cache .ruff_cache build dist/.cache
	find . -name __pycache__ -type d -exec rm -rf {} +
