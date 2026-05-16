# AMT Ontology

This repository holds the AMT ontology suite, a Flask browser for it, a set
of SHACL shapes used for validation, and the test suite that exercises both.
Everything is authored in Turtle (`.ttl`).

The suite covers four authored ontologies plus three "user views" layered on
top of two of them:

| File | What it is |
|---|---|
| `ontology/amtmeta.ttl`        | Metadata vocabulary: `Collection`, `groups`, `viewOf`, status / stewardship terms |
| `ontology/pc.ttl`             | Product Categories — the core class taxonomy |
| `ontology/ind.ttl`            | Industries — flat industry taxonomy |
| `ontology/im.ttl`             | Information Model — Visitor / Exhibitor / Company / IMTS / AMT |
| `ontology/exhibitor_view.ttl` | View of `pc.ttl` for IMTS exhibitor catalog browsing |
| `ontology/visitor_view.ttl`   | View of `pc.ttl` for IMTS visitor catalog browsing |
| `ontology/ind_view.ttl`       | View of `ind.ttl` |

Views are *not* OWL subclass trees. They are nested **`amtmeta:Collection`**
named individuals connected by **`amtmeta:groups`**: each top-level
Collection becomes a Major Category, nested Collections become Sub
Categories, and the leaf targets of `groups` resolve into the source
ontology (a `pc:` class or a catalog-grouping `amtmeta:Collection` defined
inside `pc.ttl`). The displayed label of a leaf comes from `skos:prefLabel`
on the source URI.

## Repository layout

```
.
├── ontology/                   # Turtle source files (the seven listed above)
│   └── imports/                # vendored upper ontologies (gufo.ttl, shacl.ttl)
├── app/                        # Flask application package — browser + helpers
│   ├── __init__.py
│   ├── paths.py                # absolute filesystem paths (CWD-independent)
│   ├── namespaces.py           # NS_PC / NS_IND / NS_IM / NS_AMTMETA + IRI consts
│   ├── labels.py               # rdfs:label / skos:prefLabel resolution policy
│   ├── graphs.py               # load_graph + lazy OntologyGraphs container
│   ├── properties.py           # IM per-class property + cardinality collector
│   ├── trees.py                # class-tree + view-tree builders, cycle detector
│   ├── im_cytoscape.py         # Cytoscape.js elements generator (sole IM diagram renderer)
│   ├── view_csv.py             # (Major, Sub, Product Category) CSV exporter
│   ├── view_xlsx.py            # Product Interest Category xlsx exporter
│   ├── merge.py                # merges all seven ttl files into one RDF/XML OWL
│   ├── validation.py           # pyshacl wrapper
│   └── routes.py               # Flask create_app factory and the / route
├── shapes/
│   └── view-shapes.ttl         # SHACL shapes for the user-view ontologies
├── templates/
│   └── ontology_browser.html   # Jinja template rendered by the browser
├── static/
│   ├── browser.css             # styles for the browser
│   └── browser.js              # tree controls + Cytoscape kick
├── tests/
│   ├── test_csv_export.py      # CSV export regression vs. resources/ baseline
│   ├── test_xlsx_export.py     # xlsx export semantic regression vs. resources/
│   ├── test_merge.py           # dist/amt-ontology.owl snapshot freshness check
│   ├── test_views_bridge.py    # structural + reasoner tests on the views
│   └── test_shacl_shapes.py    # SHACL validation tests
├── resources/                  # historical baselines + reference docs
│   ├── model.md                #   narrative model documentation
│   ├── IMTS Exhibitor Categories.csv
│   ├── IMTS Visitor Categories.csv
│   └── AMT Taxonomy - Product Interest Category.xlsx
├── dist/                       # checked-in build outputs (regenerable via `make dist`)
│   ├── imts_exhibitor.csv      #   exhibitor view as CSV
│   ├── imts_visitor.csv        #   visitor view as CSV
│   ├── amt-ontology.owl        #   all seven TTLs merged into one RDF/XML
│   └── AMT Taxonomy - Product Interest Category.xlsx  # visitor-view as Excel
├── ontology_ui.py              # CLI entry point — delegates to app.create_app
├── pyproject.toml              # package metadata + tool config
├── requirements.txt            # thin alias for pip install -e ".[dev,reasoner]"
├── Makefile                    # common project tasks
├── .github/workflows/ci.yml    # lint + test + dist-drift check
└── README.md
```

## Getting started

Python 3.10+ is required.

```bash
python -m venv .venv
source .venv/bin/activate                # Windows: .venv\Scripts\activate
make install                             # if you prefer make
pip install -e ".[dev,reasoner]"         # or: pip install -r requirements.txt
```

The editable install registers a `amt-browser` console script that is
equivalent to `python ontology_ui.py`.

## Running the browser

```bash
python ontology_ui.py                    # default: http://127.0.0.1:5000
python ontology_ui.py --host 0.0.0.0 --port 8080
amt-browser                              # if installed via pip install -e .
make serve                               # if you prefer make
```

`ontology_ui.py` is a thin CLI shim — it parses `--host`, `--port`, and an
optional `--ontology-dir`, then hands off to `app.create_app`. All paths
inside the app resolve from `app/paths.py` (`Path(__file__).resolve()…`)
so the server can be launched from any working directory.

### Environment-variable overrides

For deployments that want to repoint paths without code changes, every
input/output directory honours an env-var override:

| Variable             | Defaults to                |
|----------------------|----------------------------|
| `AMT_ONTOLOGY_DIR`   | `<repo>/ontology`          |
| `AMT_SHAPES_DIR`     | `<repo>/shapes`            |
| `AMT_TEMPLATE_DIR`   | `<repo>/templates`         |
| `AMT_STATIC_DIR`     | `<repo>/static`            |
| `AMT_DIST_DIR`       | `<repo>/dist`              |

Useful when the same wheel is deployed against different ontology
snapshots (staging vs production).

The browser exposes three top-level tabs:

* **Information Model** — `im.ttl` as a containment tree (Core sub-tab),
  plus a Cytoscape.js movable graph on the Interactive sub-tab.
* **Product Categories** — `pc.ttl` as a class taxonomy, plus the
  Exhibitor and Visitor views derived from it.
* **Industries** — `ind.ttl` taxonomy plus the industries view.

CSV exports of the Exhibitor and Visitor views are produced via
`make dist-csv` / `python -m app.view_csv`.

## Common commands (Makefile)

```
make help            # list available targets
make install         # pip install -e ".[dev,reasoner]"
make serve           # run the Flask dev server
make test            # full test suite
make shacl           # only the SHACL tests
make lint            # ruff check + format check
make format          # ruff format
make dist            # regenerate every artefact in dist/ (CSVs + merged OWL + xlsx)
make dist-csv        #   only the view CSVs
make dist-owl        #   only the merged amt-ontology.owl
make dist-xlsx       #   only the Product Interest Category xlsx
make clean           # remove caches
```

## CSV export

The Exhibitor and Visitor views serialise to the historical three-column
schema. Generate them with `make dist-csv` or
`python -m app.view_csv`:

| Major Category | Sub Category | Product Category |
|---|---|---|
| Additive | | Binder Jetting |
| Subtractive | Sawing | Bandsaws |

* **Major Category** — the top-level (root) Collection in the view.
* **Sub Category** — an intermediate Collection between Major and Product;
  empty when a Product is grouped directly under a Major.
* **Product Category** — `skos:prefLabel` of the leaf URI in the source
  ontology (`pc.ttl`). Leaves without a `skos:prefLabel` are silently
  dropped from the export, mirroring the browser's behaviour.

The last published exports are checked in under `dist/` for downstream
consumers that want a stable snapshot. They are regenerated by
`make dist-csv` (which calls `python -m app.view_csv dist/`). CI fails any
PR where the views and `dist/` are out of sync — run `make dist` and
commit the result in the same PR as the ontology change.

## xlsx export (`dist/AMT Taxonomy - Product Interest Category.xlsx`)

The visitor view is *also* exported as a multi-sheet xlsx that mirrors
the historical workbook AMT's taxonomy stewards have maintained by hand
(`resources/AMT Taxonomy - Product Interest Category.xlsx`). This export
is **additive** — it does not replace the CSV. Four sheets are generated:

* **Taxonomy Metadata** — name, owner, status, governors, consumers,
  stewards, related products/systems, next review date, related
  documentation, use cases, notes; sourced from `dcterms:title` and the
  `amtmeta:*` annotation properties on the view's `owl:Ontology` header.
* **Release Log** — release number, date, scope summary, owner, approval
  status, release notes URL; sourced from `owl:versionInfo` plus the
  `amtmeta:release*` properties. The terms-added/-modified/-deprecated
  columns are intentionally blank — those derive from `git diff` against
  the previous tag and live in the GitHub release body.
* **Hierarchy & Mapping** — Tier 1 / Tier 2 / Tier 3 hierarchy from the
  same data the CSV exporter produces, formatted with the historical
  Excel column layout.
* **Look-up values** — Approval Status options sourced from each
  `amtmeta:Status` individual's `skos:prefLabel`.

Regenerate with `make dist-xlsx` (or `make dist`). The test suite
(`tests/test_xlsx_export.py`) compares the generated workbook against
the resource baseline *semantically* — Tier 3 leaves must match exactly,
Tier 1 groupings must match structurally (allowing label renames),
look-up values must match as a set, and use cases match by Jaccard
fuzzy comparison (tolerant of typos like `Passprt` in the historical
workbook).

## Merged OWL distribution (`dist/amt-ontology.owl`)

The seven authored TTL files are also published as a single merged RDF/XML
file at `dist/amt-ontology.owl`. It is what a downstream consumer wants
when it needs the whole AMT vocabulary in one place — Protégé in
"open one file" mode, an archival snapshot, or a tool that doesn't
follow `owl:imports`.

What's in it:

* every logical axiom from `amtmeta`, `pc`, `ind`, `im`, and the three
  view files (classes, properties, individuals, restrictions, labels,
  prefLabels);
* exactly one `owl:Ontology` declaration at IRI
  `http://ontology.amt.org/amt-ontology` carrying `owl:versionInfo` (the
  highest per-file version) and an `rdfs:comment` listing the contributing
  file names + versions for traceability;
* external `owl:imports` for **gufo** and **shacl** — the upper
  ontologies are *referenced*, not inlined, so the merged file stays
  consumable by tools that already have those on hand;
* no internal AMT cross-imports (e.g. `pc` no longer imports `amtmeta`),
  because they would be redundant in a single-file merge.

Regenerate with `make dist-owl` (or `make dist`). The merger is
**content-idempotent**: if the TTL state hasn't changed semantically the
output file is left untouched, so `git diff dist/amt-ontology.owl` only
fires on real ontology changes. CI enforces this via the
"dist/ matches current ontology" step.

## Validation

Six layers of validation, all runnable via `make test` or
`python -m unittest discover -s tests`:

1. **Structural (`tests/test_views_bridge.py`)** — for each view file:
   * every `amtmeta:Collection` carries an `rdfs:label`;
   * every `amtmeta:groups` target resolves to either another Collection
     in this view or a URI declared in the source ontology;
   * the Collection-grouping graph is acyclic and fully reachable from a
     top-level Major;
   * the view declares `amtmeta:viewOf` pointing at the source ontology
     IRI.

   All helpers used here come from `app.trees` and `app.graphs`, so the
   browser and the tests share one definition of what a Collection is.

2. **SHACL (`tests/test_shacl_shapes.py`)** — validates each
   `view + source` pair against `shapes/view-shapes.ttl` via
   [`pyshacl`](https://github.com/RDFLib/pySHACL). The shapes enforce:
   * `amtmeta:Collection` ⇒ at least one `rdfs:label`;
   * `amtmeta:groups` targets must be IRIs and must resolve to either an
     `amtmeta:Collection` or an `owl:Class` in the data graph;
   * `amtmeta:viewOf` values must be IRIs.

3. **CSV-baseline regression (`tests/test_csv_export.py`)** — the CSV
   produced by the live exporter for each view must match the original
   seed file in `resources/` byte-for-byte:
   * `exhibitor_view.ttl` → `resources/IMTS Exhibitor Categories.csv`
   * `visitor_view.ttl`   → `resources/IMTS Visitor Categories.csv`

   These CSVs predate the ontology effort and are the source-of-truth
   the views were authored against. If the test fails it prints a
   row-level diff (rows added / removed) and the exact commands to
   refresh the baseline if the change is intentional.

4. **xlsx semantic regression (`tests/test_xlsx_export.py`)** — the
   workbook produced by `python -m app.view_xlsx` for the visitor view
   must match the historical AMT-maintained workbook
   (`resources/AMT Taxonomy - Product Interest Category.xlsx`)
   *semantically* (not byte-for-byte — cell styling, column widths, and
   the omitted SAMPLE / Previous-versions sheets diverge intentionally).
   Nine sub-checks:
   * required sheet names present;
   * Taxonomy Metadata field labels match;
   * Status and Taxonomy owner values match exactly;
   * use cases match by Jaccard fuzzy comparison (≥ 0.7), tolerating
     typos such as `Passprt` ↔ `Passport` in the resource;
   * Look-up values match as a set (Draft / Pending Review / Approved /
     Deprecated);
   * Release Log column headers match exactly;
   * Tier 3 leaf set matches exactly;
   * Tier 1 grouping structure is preserved even under label renames
     (e.g. `Industrial Artificial Intelligence` → `Industrial AI`).

5. **Merge snapshot freshness (`tests/test_merge.py`)** — the
   triple-count of `dist/amt-ontology.owl` must match a fresh merge of
   the current TTL files. Catches PRs that change the ontology without
   refreshing the merged distribution. If it fails: `make dist-owl` (or
   `make dist`) and commit the result.

6. **OWL reasoner (`TestOwlreadyConsistency`, optional)** — converts
   the TTL files to RDF/XML on the fly, resolves imports against
   `ontology/imports/` (gufo + shacl), and runs a DL reasoner over each
   view. HermiT is tried first; Pellet is used as a fallback (HermiT
   does not support `xsd:date`, which `im.ttl` uses for
   `registrationDate`). The test skips automatically if neither reasoner
   can run.

   **Prerequisites for running this layer locally:**

   * A working Java runtime (`java -version` should print a version).
     Owlready2 ships HermiT and Pellet as JARs and shells out to `java`
     to execute them — so installing the Python package isn't enough on
     its own. On Windows install the *Temurin* or *Oracle* JDK and make
     sure it's on `PATH`. On macOS: `brew install --cask temurin`. On
     Debian/Ubuntu: `sudo apt install default-jre`.
   * The `reasoner` extra installed: `pip install -e ".[reasoner]"`
     (or `make install`, which adds it by default).

   To run just this layer with verbose output:

   ```bash
   make reasoner-check
   ```

   On our data **HermiT will always fail and Pellet will run** — the
   skip message is informative if neither succeeds. If both fail check
   that `java` is on `PATH` and that the gufo + shacl files are present
   in `ontology/imports/` (both are vendored in the repo).

## Conventions

These are the conventions every file in the repo already follows; codifying
them keeps future PRs consistent.

### Namespaces

One namespace per authored ontology, plus the metadata vocabulary:

| Prefix    | Namespace URI                                       |
|-----------|------------------------------------------------------|
| `amtmeta` | `http://ontology.amt.org/meta#`                      |
| `pc`      | `http://ontology.amt.org/product-categories#`        |
| `ind`     | `http://ontology.amt.org/industries#`                |
| `im`      | `http://ontology.amt.org/im#`                        |

The matching **ontology IRIs** (object of `owl:imports` and
`amtmeta:viewOf`) drop the trailing `#`. View ontologies live under
`http://ontology.amt.org/views/<slug>` where `<slug>` is the filename
stem without `_view` — `exhibitor`, `visitor`, `industries`.

### URI fragment style

* **Classes** — UpperCamelCase (`ManufacturingDevice`, `LaserCuttingSystem`).
* **Properties** — lowerCamelCase (`taxonomyOwner`, `groups`, `viewOf`).
* **`amtmeta:Collection` individuals** — UpperCamelCase with the suffix
  `Collection` (`LaserTechnologyCollection`, `SawingMachineOtherCollection`).
  The suffix is what marks a node as a catalog grouping vs. a real class.
* **Catalog residual ("Other") buckets** — same Collection suffix with
  `Other` baked into the local name (`SawingMachineOtherCollection`).
* **No digits at the start of a fragment**; use `C_` prefix if you must
  (`C_3DPrintingAdditiveMfg`).
* No underscores or hyphens in fragments. The old `csv_to_rdf.py`
  pipeline used underscores — that style was retired, don't bring it back.

### Labels

* **`rdfs:label`** — always present on classes, properties, Collections,
  and named individuals. Human-readable display string.
* **`skos:prefLabel`** — the leaf marker. Its presence on a pc-side
  entity tells the view tree and the CSV exporter "this is a leaf;
  don't expand it, and use this string as the user-facing name."
* **No label** → fallback to the URI local name with underscores
  humanised (see `app.labels.get_label`).
* When the same URI is labelled in both the view file and the source
  ontology, the source wins for display. Full lookup order is in
  `app.labels.view_label`.

### Ontology metadata

Every authored ontology declares:

* `dcterms:title` — human title.
* `owl:versionInfo` — semver string (`MAJOR.MINOR.PATCH`).
* `owl:imports` — every upstream ontology required at reasoning time.
* a second `rdf:type` from `{ amtmeta:Taxonomy, amtmeta:UserView,
  amtmeta:InformationModel }` — distinguishes its role.

Stewardship / lifecycle annotation properties (all multi-valued unless
noted):

* `amtmeta:status` ∈ `{ amtmeta:Draft, amtmeta:UnderReview, amtmeta:Active }`
  (single)
* `amtmeta:taxonomyOwner`, `amtmeta:technicalSteward` (single)
* `amtmeta:governedBy`, `amtmeta:consumedBy`
* `amtmeta:relatedProduct`, `amtmeta:relatedSystem`
* `amtmeta:nextReviewDate` (`xsd:date`, single) + optional
  `amtmeta:nextReviewNote`
* `amtmeta:useCase`
* `rdfs:seeAlso`

### Versioning

Each ontology carries its own `owl:versionInfo`; there is no global
"repo version" for the ontologies (the version in `pyproject.toml` is
the *code* version). Bump the relevant file's version in the same PR
as the change. Base taxonomies (`pc`, `ind`) move slowly; views and the
IM evolve faster. When publishing, tag the commit per file (e.g.
`pc-v0.1.0`, `exhibitor_view-v0.2.2`) so downstream consumers can pin
without coupling pc to view bumps.

### SHACL shapes

Shapes live under `shapes/`. One file per shape family:
`view-shapes.ttl` covers the union of any view + its source. Every
shape carries an `sh:message` written in the imperative — those
strings end up in CI logs. New shapes get a matching test class in
`tests/test_shacl_shapes.py`.

### Pull-request checklist

Before opening a PR that touches an ontology file:

1. Bump `owl:versionInfo` in any file you changed.
2. `make test` — structural + SHACL must pass.
3. `make dist` — if `git diff dist/` is non-empty, commit the result
   in the same PR. CI fails otherwise.
4. Any new Collection has both `rdfs:label` and (for leaf-grouping)
   `skos:prefLabel`.
5. Any new IRI fragment matches the style above.

## Resources

`resources/model.md` is the human-editable Markdown outline of the Product
Category hierarchy used as the original source-of-truth for `pc.ttl`. The
`resources/IMTS *.csv` files are the raw category lists that earlier
versions of the pipeline consumed; today the views are authored directly
against `pc.ttl` and these files are kept for historical reference.

## Dependencies

Declared in `pyproject.toml`. Runtime:

* `Flask`     — the browser
* `rdflib`    — ontology parsing
* `pyshacl`   — SHACL validation

Optional extras:

* `reasoner` — adds `owlready2` (HermiT/Pellet reasoner tests)
* `dev`      — adds `pytest`, `pytest-cov`, `ruff`
