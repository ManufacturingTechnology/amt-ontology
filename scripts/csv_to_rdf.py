import pandas as pd
from owlready2 import *
import types
import argparse
import os

BASE_USER_DOMAIN = "http://ontology.amt.org/users/"

# A local cache to avoid hitting the owlready2 database for lookups
USER_CLASS_CACHE = {}

def get_user_class_cached(name, parent, user_onto):
    """Uses a local dict to avoid the namespace lookup hang."""
    safe_name = name.strip().replace(" ", "_").replace("-", "_")
    
    if safe_name in USER_CLASS_CACHE:
        return USER_CLASS_CACHE[safe_name]
    
    with user_onto:
        # Create the class directly
        new_cls = types.new_class(safe_name, (parent,))
        new_cls.label = [name.strip()]
        # Store in our local cache
        USER_CLASS_CACHE[safe_name] = new_cls
    return new_cls

def build_bridge(csv_path, cat_onto, user_onto):
    print(f"Reading CSV: {csv_path}")
    # We use keep_default_na=False to handle empty cells as empty strings instead of NaN
    df = pd.read_csv(csv_path, keep_default_na=False)
    
    print("Pre-indexing core labels...")
    core_label_map = {}
    for c in cat_onto.classes():
        labels = c.label
        if labels:
            core_label_map[str(labels[0]).strip()] = c

    print("Building User Hierarchy...")
    for idx, row in df.iterrows():
        # Clean up the values
        major_val = str(row.get("Major Category", "")).strip()
        sub_val = str(row.get("Sub Category", "")).strip()
        prod_val = str(row.get("Product Category", "")).strip()

        # Validation: Skip if mandatory fields are missing
        if not major_val or not prod_val:
            continue

        # 1. Create Major Class
        major_cls = get_user_class_cached(major_val, Thing, user_onto)

        # 2. Determine Parent for Product Category
        if sub_val and sub_val.lower() != "nan" and sub_val != "":
            # If sub exists, create it under major, and prod goes under sub
            sub_cls = get_user_class_cached(sub_val, major_cls, user_onto)
            parent_for_prod = sub_cls
        else:
            # If sub is missing, prod goes directly under major
            parent_for_prod = major_cls

        # 3. Create Product Category
        prod_cls = get_user_class_cached(prod_val, parent_for_prod, user_onto)

        # 4. Link to Core
        core_cls = core_label_map.get(prod_val)
        if core_cls:
            if core_cls not in prod_cls.equivalent_to:
                prod_cls.equivalent_to.append(core_cls)
        
        if (idx + 1) % 100 == 0:
            print(f"Processed {idx + 1} rows...")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--filename", required=True)
    parser.add_argument("--ns", required=True)
    parser.add_argument("--core", required=True)
    args = parser.parse_args()

    # Create a fresh world
    default_world.graph.close() # Close global graph just in case
    my_world = World()
    
    specific_user_iri = f"{BASE_USER_DOMAIN}{args.ns}#"
    core_file_path = os.path.abspath(args.core)

    print(f"--- Loading Core ---")
    # Load core WITHOUT specifying it as an import yet
    cat_onto = my_world.get_ontology(core_file_path).load()
    
    print(f"--- Creating Bridge ---")
    user_onto = my_world.get_ontology(specific_user_iri)
    
    # DO NOT append to imported_ontologies yet. 
    # Let's see if the build finishes without the overhead of the import link.
    
    if os.path.exists(args.filename):
        build_bridge(args.filename, cat_onto, user_onto)
        
        # NOW, right before saving, add the import link
        print("Finalizing ontology imports...")
        user_onto.imported_ontologies.append(cat_onto)
        
        output_dir = "ontology"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"user-bridge-{args.ns}.owl")
        
        print(f"Saving to {output_path}...")
        user_onto.save(output_path, format="rdfxml")
        print("Done!")
    else:
        print("CSV not found.")