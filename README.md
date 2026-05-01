# Product Category Ontology

This repository contains the ontology model, source resources, and automation scripts for the AMT Ontology project. It specifically focuses on Product Category model and bridging IMTS (International Manufacturing Technology Show) exhibitor and visitor data with semantic web structures.

## Project Structure

AMT-ONTOLOGY/
├── dist/                   # Generated output data (CSV format)
├── ontology/               # OWL ontology files; core and user-bridge ontologies
├── resources/              # Source CSV data and markdown models
├── scripts/                # Python utility scripts for data transformation
├── templates/              # HTML templates for the ontology browser
├── ontology_ui.py          # Main UI application for interacting with the ontology
├── requirements.txt        # Python dependencies
└── README.md               # Project documentation


## Components

### Ontology (/ontology)

Contains the core semantic models:

`product-categories-v1.owl`: The base taxonomy for product categorization.

`user-bridge-imts-exhibitor.owl`: Mapping logic for exhibitor categories.

`user-bridge-imts-visitor.owl`: Mapping logic for visitor categories.

`catalog-v001.xml`: Protégé configuration for managing file dependencies.

### Scripts (/scripts)

Automation tools to move data between formats:

`csv_to_rdf.py`: Converts raw source IMTS CSV data into user bridge RDF/OWL triples.

`rdf_to_csv.py`: Exports data from the ontology back into flat CSV files.

`md_to_rdf.py`: Parses the model.md documentation into core product category ontology.

`compare_csv_diff.py`: Utility to track changes between source and dist versions of the csv data.

### Resources & Dist (/resources, /dist)

`Resources`: Source files used to creat user-bridge mapping to core ontology.

`Dist`: The final processed output files (imts_exhibitor.csv, imts_visitor.csv) ready for production use.

## Getting Started

### Prerequisites

Ensure you have Python 3.x installed. It is recommended to use a virtual environment.

### Installation

Clone the repository:

    git clone https://github.com/your-repo/amt-ontology.git
    cd amt-ontology

Install dependencies:

    pip install -r requirements.txt

## Usage

Distribution ready outputs already available in `/dist`

To download from UI follow the steps below:

Run the UI

    python ontology_ui.py

Open UI in browser (assuming default ip and ports used)

    127.0.0.1/5000

Go to relevant tab and download relevant CSV.


## Create OWL from MD

python .\scripts\md_to_rdf.py
