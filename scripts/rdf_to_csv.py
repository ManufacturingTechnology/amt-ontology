import pandas as pd
from owlready2 import *
import os
import argparse

def export_to_csv(user_onto, output_csv_path):
    rows = []
    
    # 1. Identify "Major Categories" 
    # These are classes in the user namespace whose only parent is 'Thing'
    major_categories = [
        c for c in user_onto.classes() 
        if Thing in c.is_a and c.namespace == user_onto
    ]

    print(f"Found {len(major_categories)} Major Categories. Exporting...")

    for major in major_categories:
        major_label = major.label[0] if major.label else major.name
        
        # Get immediate subclasses
        children = list(major.subclasses())
        
        if not children:
            # Case: Major category with no children (Optional handling)
            continue

        for child in children:
            # We determine if the child is a "Sub Category" or a "Product Category"
            # Logic: If the child has further subclasses, it's a Sub Category.
            # If it has NO subclasses, it's a Product Category.
            
            grandchildren = list(child.subclasses())
            
            if grandchildren:
                # This child is a SUB CATEGORY
                sub_label = child.label[0] if child.label else child.name
                for gchild in grandchildren:
                    prod_label = gchild.label[0] if gchild.label else gchild.name
                    rows.append({
                        "Major Category": major_label,
                        "Sub Category": sub_label,
                        "Product Category": prod_label
                    })
            else:
                # This child is a PRODUCT CATEGORY (Directly under Major)
                prod_label = child.label[0] if child.label else child.name
                rows.append({
                    "Major Category": major_label,
                    "Sub Category": "",  # Keep empty as requested
                    "Product Category": prod_label
                })

    # Create DataFrame and Save
    df = pd.DataFrame(rows)
    # Reorder columns to ensure correct format
    df = df[["Major Category", "Sub Category", "Product Category"]]
    df.to_csv(output_csv_path, index=False)
    print(f"Successfully exported {len(df)} rows to {output_csv_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export User Bridge Ontology to CSV.")
    parser.add_argument("--ontology", required=True, help="Path to the .owl user bridge file.")
    parser.add_argument("--core", required=True, help="Path to the local Core .owl file.")
    parser.add_argument("--output", default="exported_user_data.csv", help="Path for the output CSV.")
    args = parser.parse_args()

    # 1. Create a World
    my_world = World()

    # 2. Add the directories to the search path
    core_path = os.path.abspath(args.core)
    user_path = os.path.abspath(args.ontology)
    onto_path.append(os.path.dirname(core_path))
    onto_path.append(os.path.dirname(user_path))

    print(f"Loading local Core Ontology first: {core_path}")
    try:
        # Loading the core first satisfies the 'import' requirement of the bridge
        my_world.get_ontology(core_path).load()
    except Exception as e:
        print(f"Warning: Could not pre-load core, export might fail if imports are strict: {e}")

    print(f"Loading User Bridge: {user_path}")
    try:
        # Now load the user ontology from the same world
        user_onto = my_world.get_ontology(user_path).load()
    except Exception as e:
        print(f"Error loading user ontology: {e}")
        exit(1)

    export_to_csv(user_onto, args.output)