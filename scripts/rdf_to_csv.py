"""
rdf_to_csv.py
=============
Export a user bridge OWL ontology back into a three-column category CSV.

The script reads a bridge ontology (produced by ``csv_to_rdf.py``) and
reconstructs the Major Category → Sub Category → Product Category hierarchy
by inspecting the class structure within the user namespace.

Classification rules applied during export
------------------------------------------
- **Major Category**: classes in the user ontology namespace whose only
  declared superclass is ``owl:Thing``.
- **Sub Category**: immediate children of a Major class that themselves have
  further subclasses.
- **Product Category**: leaf classes (no subclasses), either directly under a
  Major class or under a Sub class.

Output CSV columns
------------------
    Major Category, Sub Category, Product Category

Usage
-----
    python rdf_to_csv.py --ontology <bridge.owl> \\
                         --core <core.owl> \\
                         [--output <output.csv>]
"""

import argparse
import os

import pandas as pd
from owlready2 import Thing, World, onto_path


def export_to_csv(user_onto, output_csv_path: str) -> None:
    """
    Walk the user bridge ontology class hierarchy and write a three-column CSV.

    Parameters
    ----------
    user_onto : owlready2.Ontology
        Loaded bridge ontology whose classes belong to the user namespace.
    output_csv_path : str
        Destination path for the output CSV file.
    """
    rows = []

    # Major categories: classes in the user namespace whose only superclass is Thing
    major_categories = [
        c
        for c in user_onto.classes()
        if Thing in c.is_a and c.namespace == user_onto
    ]
    print(f"Found {len(major_categories)} major categories. Exporting...")

    for major in major_categories:
        major_label = major.label[0] if major.label else major.name

        for child in major.subclasses():
            grandchildren = list(child.subclasses())

            if grandchildren:
                # Child is a Sub Category
                sub_label = child.label[0] if child.label else child.name
                for grandchild in grandchildren:
                    prod_label = grandchild.label[0] if grandchild.label else grandchild.name
                    rows.append({
                        "Major Category": major_label,
                        "Sub Category": sub_label,
                        "Product Category": prod_label,
                    })
            else:
                # Child is a Product Category directly under Major
                prod_label = child.label[0] if child.label else child.name
                rows.append({
                    "Major Category": major_label,
                    "Sub Category": "",
                    "Product Category": prod_label,
                })

    df = pd.DataFrame(rows, columns=["Major Category", "Sub Category", "Product Category"])
    df.to_csv(output_csv_path, index=False)
    print(f"Exported {len(df)} rows to {output_csv_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export a user bridge OWL ontology to a three-column category CSV."
    )
    parser.add_argument(
        "--ontology", required=True, help="Path to the user bridge .owl file."
    )
    parser.add_argument(
        "--core", required=True, help="Path to the core product-category .owl file."
    )
    parser.add_argument(
        "--output",
        default="exported_user_data.csv",
        help="Destination path for the output CSV (default: exported_user_data.csv).",
    )
    args = parser.parse_args()

    my_world = World()

    core_path = os.path.abspath(args.core)
    user_path = os.path.abspath(args.ontology)

    # Add both directories to owlready2's search path so that import
    # declarations in the bridge file can resolve the core ontology locally
    onto_path.append(os.path.dirname(core_path))
    onto_path.append(os.path.dirname(user_path))

    print(f"Loading core ontology: {core_path}")
    try:
        my_world.get_ontology(core_path).load()
    except Exception as exc:
        print(f"Warning: Could not pre-load core ontology ({exc}). Import resolution may fail.")

    print(f"Loading user bridge ontology: {user_path}")
    try:
        user_onto = my_world.get_ontology(user_path).load()
    except Exception as exc:
        print(f"Error: Could not load user bridge ontology: {exc}")
        raise SystemExit(1)

    export_to_csv(user_onto, args.output)