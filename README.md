# Product Category Ontology

This repository contains the ontology model, source resources, and automation scripts for the AMT Ontology project. It focuses on Product Category model and bridges IMTS (International Manufacturing Technology Show) exhibitor and visitor data with semantic web structures using OWL ontologies.

## Project Structure

```
AMT-ONTOLOGY/
├── dist/                   # Generated output CSVs ready for production
├── ontology/               # OWL ontology files; core and user-bridge ontologies
├── resources/              # Source data and Markdown models
├── scripts/                # Data transformation utilities
├── templates/              # HTML templates for the ontology browser
├── ontology_ui.py          # Flask web application for the ontology browser
├── requirements.txt        # Python dependencies
└── README.md               # Project documentation
```

## Components

### Ontology (/ontology)

| File | Description |
|---|---|
| `product-categories-v1.owl` | Base product taxonomy; generated from `model.md` via `md_to_rdf.py`. |
| `user-bridge-imts-exhibitor.owl` | Bridge ontology mapping IMTS exhibitor categories to the core taxonomy. |
| `user-bridge-imts-visitor.owl` | Bridge ontology mapping IMTS visitor categories to the core taxonomy. |
| `catalog-v001.xml` | Protégé XML catalog for resolving local ontology imports. |

The bridge ontologies link user-defined category labels to core taxonomy classes via `owl:equivalentClass` axioms, enabling reasoning across both hierarchies.

### Scripts (/scripts)

| Script | Description |
|---|---|
| `md_to_rdf.py` | Parses `resources/model.md` (nested bullet list) into `product-categories-v1.owl`. Run this first when the core taxonomy changes. |
| `csv_to_rdf.py` | Converts a three-column category CSV into a user bridge OWL ontology. Accepts `--filename`, `--ns`, and `--core` arguments. |
| `rdf_to_csv.py` | Exports a user bridge ontology back to a flat three-column CSV. Accepts `--ontology`, `--core`, and `--output` arguments. |
| `compare_csv_diff.py` | Diffs two CSVs on configurable key columns and reports added/removed rows. Useful for auditing changes between `resources/` and `dist/`. |

### Web UI (`ontology_ui.py`)

A Flask application that provides a browser-based view of the ontology hierarchy and CSV export functionality.

- **Core tab** — browses the full `product-categories-v1.owl` class tree (up to 4 levels deep) using owlready2. The HermiT reasoner runs once at startup so all inferred facts are available.
- **Exhibitor / Visitor tabs** — browse the respective bridge ontology class trees, including `owl:equivalentClass` links back to the core taxonomy.
- **CSV download** — exports the three-level Major → Sub → Product hierarchy for either bridge ontology directly from the UI.

### Resources & Dist (`/resources`, `/dist`)

| Directory | Purpose |
|---|---|
| `resources/` | Source files: the `model.md` taxonomy definition and the raw IMTS category CSVs used to generate the bridge ontologies. |
| `dist/` | Production-ready output CSVs (`imts_exhibitor.csv`, `imts_visitor.csv`) exported from the bridge ontologies. |

---

## Getting Started

### Prerequisites

- Python 3.10 or later (walrus operator and union type hints are used)
- A virtual environment is strongly recommended

### Installation

```bash
git clone https://github.com/your-repo/amt-ontology.git
cd amt-ontology
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

### Run the ontology browser

```bash
python ontology_ui.py
# Custom host/port:
python ontology_ui.py --host 0.0.0.0 --port 8080
```

Open in browser: [http://127.0.0.1:5000](http://127.0.0.1:5000)

Navigate to the **Exhibitor** or **Visitor** tab and click **Download CSV** to export the category hierarchy.

> Production-ready CSVs are already available in `/dist` if you do not need to regenerate them.

---

## Data Pipeline

The scripts form a one-way pipeline. Run them in the order below when rebuilding from source.

```
model.md  ──(md_to_rdf.py)──►  product-categories-v1.owl  (core)
                                         │
resources/*.csv  ──(csv_to_rdf.py)──►  user-bridge-*.owl  (bridge)
                                         │
                          ──(rdf_to_csv.py)──►  dist/*.csv
```

### 1. Rebuild the core ontology from Markdown

```bash
python scripts/md_to_rdf.py
```

Reads `resources/model.md` and writes `ontology/product-categories-v1.owl`.

### 2. Build a bridge ontology from a category CSV

```bash
python scripts/csv_to_rdf.py \
    --filename "resources/IMTS Exhibitor Categories.csv" \
    --ns imts-exhibitor \
    --core ontology/product-categories-v1.owl
```

Writes `ontology/user-bridge-imts-exhibitor.owl`. Replace `--ns` and `--filename` for the visitor bridge.

### 3. Export a bridge ontology back to CSV

```bash
python scripts/rdf_to_csv.py \
    --ontology ontology/user-bridge-imts-exhibitor.owl \
    --core ontology/product-categories-v1.owl \
    --output dist/imts_exhibitor.csv
```

### 4. Audit changes between two CSV versions

```bash
python scripts/compare_csv_diff.py \
    dist/imts_exhibitor.csv \
    "resources/IMTS Exhibitor Categories.csv"
```

Uses `Major Category`, `Sub Category`, and `Product Category` as the composite key by default. Pass `--keys` to override.

---

## CSV Format

All source and output CSVs share the same three-column schema:

| Major Category | Sub Category | Product Category |
|---|---|---|
| Additive | | Binder Jetting |
| Subtractive | Sawing | Bandsaws |

- **Major Category** — required; top-level grouping.
- **Sub Category** — optional; intermediate grouping between Major and Product.
- **Product Category** — required; leaf-level category linked to the core ontology via `owl:equivalentClass`.

Rows with an empty `Major` or `Product Category` are skipped during ontology generation.
