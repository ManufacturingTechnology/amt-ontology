"""
csv_to_rdf.py
=============
Convert a three-column category CSV into an OWL bridge ontology that links
user-defined category labels to the AMT core product-category ontology via
``owl:equivalentClass`` axioms.

CSV format
----------
The input CSV must have exactly these three columns (empty cells are allowed):

    Major Category | Sub Category | Product Category

Hierarchy rules
---------------
- **Major** classes are direct children of ``owl:Thing``.
- **Sub** classes (optional) are children of their Major class.
- **Product** classes are children of their Sub class, or directly under their
  Major class when Sub is absent.
- When a Product label matches a class label in the core ontology, an
  ``owl:equivalentClass`` axiom is added automatically.

Output
------
The bridge ontology is saved as RDF/XML to ``ontology/user-bridge-<ns>.owl``.

Usage
-----
    python csv_to_rdf.py --filename <path/to/categories.csv> \\
                         --ns <namespace-slug> \\
                         --core <path/to/core.owl>

Example
-------
    python csv_to_rdf.py \\
        --filename "IMTS Exhibitor Categories.csv" \\
        --ns imts-exhibitor \\
        --core ontology/product-categories-v1.owl
"""

import argparse
import os
import types

import pandas as pd
from owlready2 import Thing, World

# Base IRI for all user bridge ontologies
BASE_USER_DOMAIN = "http://ontology.amt.org/users/"

# Module-level cache: safe class name → owlready2 class object.
# Avoids repeated owlready2 namespace lookups, which can be slow on large
# ontologies.
_USER_CLASS_CACHE: dict[str, type] = {}


def _safe_name(label: str) -> str:
    """
    Convert a human-readable label into a valid OWL class name (no spaces or
    hyphens).

    Parameters
    ----------
    label : str
        Raw category label, e.g. ``"CNC Milling – 5-Axis"``.

    Returns
    -------
    str
        Underscore-normalised identifier, e.g. ``"CNC_Milling_5_Axis"``.
    """
    return label.strip().replace(" ", "_").replace("-", "_")


def get_or_create_class(label: str, parent: type, user_onto) -> type:
    """
    Return an existing owlready2 class for *label*, or create one under
    *parent* if it does not yet exist.

    The class is stored in the module-level ``_USER_CLASS_CACHE`` to avoid
    redundant ontology lookups.

    Parameters
    ----------
    label : str
        Human-readable category label (used as ``rdfs:label``).
    parent : type
        Owlready2 class that will be the direct superclass.
    user_onto : owlready2.Ontology
        The bridge ontology in which to create the new class.

    Returns
    -------
    type
        The owlready2 class object.
    """
    safe = _safe_name(label)
    if safe in _USER_CLASS_CACHE:
        return _USER_CLASS_CACHE[safe]

    with user_onto:
        new_cls = types.new_class(safe, (parent,))
        new_cls.label = [label.strip()]
        _USER_CLASS_CACHE[safe] = new_cls

    return new_cls


def build_bridge(csv_path: str, cat_onto, user_onto) -> None:
    """
    Read the CSV at *csv_path* and populate *user_onto* with the three-level
    class hierarchy, linking Product classes to *cat_onto* via
    ``owl:equivalentClass`` where labels match.

    Parameters
    ----------
    csv_path : str
        Path to the input CSV file.
    cat_onto : owlready2.Ontology
        Pre-loaded core product-category ontology used for equivalence linking.
    user_onto : owlready2.Ontology
        Target bridge ontology (written to in place).
    """
    print(f"Reading CSV: {csv_path}")
    df = pd.read_csv(csv_path, keep_default_na=False)

    # Pre-index core labels once for O(1) look-ups during row processing
    print("Pre-indexing core ontology labels...")
    core_label_map: dict[str, type] = {
        str(c.label[0]).strip(): c
        for c in cat_onto.classes()
        if c.label
    }

    print("Building user class hierarchy...")
    for idx, row in df.iterrows():
        major_val = str(row.get("Major Category", "")).strip()
        sub_val = str(row.get("Sub Category", "")).strip()
        prod_val = str(row.get("Product Category", "")).strip()

        # Skip rows that are missing either mandatory boundary classes
        if not major_val or not prod_val:
            continue

        major_cls = get_or_create_class(major_val, Thing, user_onto)

        if sub_val and sub_val.lower() != "nan":
            sub_cls = get_or_create_class(sub_val, major_cls, user_onto)
            parent_for_prod = sub_cls
        else:
            parent_for_prod = major_cls

        prod_cls = get_or_create_class(prod_val, parent_for_prod, user_onto)

        # Link to core ontology if label matches
        core_cls = core_label_map.get(prod_val)
        if core_cls and core_cls not in prod_cls.equivalent_to:
            prod_cls.equivalent_to.append(core_cls)

        if (idx + 1) % 100 == 0:
            print(f"  Processed {idx + 1} rows...")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build an OWL bridge ontology from a three-column category CSV."
    )
    parser.add_argument("--filename", required=True, help="Path to the input CSV file.")
    parser.add_argument(
        "--ns",
        required=True,
        help="Namespace slug used in the output filename and ontology IRI (e.g. imts-exhibitor).",
    )
    parser.add_argument("--core", required=True, help="Path to the core .owl ontology file.")
    args = parser.parse_args()

    if not os.path.exists(args.filename):
        print(f"Error: CSV file not found: {args.filename}")
        raise SystemExit(1)

    # Use a private World to avoid polluting the owlready2 global default world
    my_world = World()

    specific_user_iri = f"{BASE_USER_DOMAIN}{args.ns}#"
    core_file_path = os.path.abspath(args.core)

    print("--- Loading Core Ontology ---")
    cat_onto = my_world.get_ontology(core_file_path).load()

    print("--- Creating Bridge Ontology ---")
    user_onto = my_world.get_ontology(specific_user_iri)

    build_bridge(args.filename, cat_onto, user_onto)

    # Add the import link only after the hierarchy is fully built to avoid
    # owlready2 overhead during class creation
    print("Finalizing ontology import declarations...")
    user_onto.imported_ontologies.append(cat_onto)

    output_dir = "ontology"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"user-bridge-{args.ns}.owl")

    print(f"Saving bridge ontology to {output_path}...")
    user_onto.save(output_path, format="rdfxml")
    print("Done.")