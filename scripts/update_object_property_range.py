import pandas as pd
from owlready2 import *

INPUT_FILE = "ontology/amt-ontology-draft2.owl"
OUTPUT_FILE = "ontology/amt-ontology.owl"
EXHIBITOR_CSV = "resources/imts_exhibitor_categories.csv"
VISITOR_CSV = "resources/imts_visitor_categories.csv"

# -----------------------------
# Load ontology
# -----------------------------

onto = get_ontology(INPUT_FILE).load()

# -----------------------------
# CSV → mapping helpers
# -----------------------------

def create_category_mapping(csv_path: str):
    """
    Map Product Category -> composed label 'Major > Sub' or 'Major'
    """
    df = pd.read_csv(csv_path)
    mapping = {}

    for _, row in df.iterrows():
        major_raw = row.get("Major Category", "")
        sub_raw = row.get("Sub Category", "")
        prod_raw = row.get("Product Category", "")

        major = str(major_raw).strip() if pd.notna(major_raw) else ""
        sub = str(sub_raw).strip() if pd.notna(sub_raw) else ""
        product = str(prod_raw).strip() if pd.notna(prod_raw) else ""

        if not product:
            continue

        if sub:
            composed = f"{major} > {sub}"
        else:
            composed = major

        mapping[product] = composed

    return mapping

print("Loading CSVs...")
exhibitor_mapping = create_category_mapping(EXHIBITOR_CSV)
visitor_mapping   = create_category_mapping(VISITOR_CSV)
print(f"Exhibitor mappings: {len(exhibitor_mapping)}")
print(f"Visitor mappings:   {len(visitor_mapping)}")

# -----------------------------
# Ontology helpers
# -----------------------------

def get_label(cls: ThingClass) -> str:
    return cls.label[0] if getattr(cls, "label", None) else cls.name

def collect_user_classes():
    """All classes in the User subtree (User_ format or nested under User)."""
    user_classes = []

    # find User root by label
    User = next(
        (c for c in onto.classes()
         if getattr(c, "label", None) and any(lbl == "User" for lbl in c.label)),
        None,
    )

    if not User:
        print("⚠ User class not found; User subtree search will be empty")
        return user_classes

    def recurse(c):
        for sub in c.subclasses():
            user_classes.append(sub)
            recurse(sub)

    recurse(User)
    return user_classes

user_classes = list(collect_user_classes())
print(f"User subtree classes: {len(user_classes)}")

def find_user_class_by_label(label: str):
    for c in user_classes:
        if getattr(c, "label", None) and any(lbl == label for lbl in c.label):
            return c
    return None

# -----------------------------
# Generic updater for both props
# -----------------------------

def update_restrictions(obj_prop, mapping, mapping_name):
    """
    Replace '<obj_prop> some IMTS Registration' with
    '<obj_prop> some <User category>' using mapping(Product→Composed).
    """
    if not hasattr(onto, obj_prop.name):
        raise RuntimeError(f"Object property {obj_prop.name} not found in ontology")

    print(f"\nUpdating {mapping_name} restrictions for property {obj_prop.name}...")
    updated = 0

    for cls in list(onto.classes()):
        cls_label = get_label(cls)
        if cls_label not in mapping:
            continue

        target_label = mapping[cls_label]
        target_user_class = find_user_class_by_label(target_label)
        if not target_user_class:
            print(f"⚠ No User class with label '{target_label}' found for product '{cls_label}'")
            continue

        new_is_a = []
        changed_here = False

        for ax in cls.is_a:
            # Look for subclass restriction: obj_prop some IMTS Registration
            if isinstance(ax, Restriction) and ax.property is obj_prop:
                filler = ax.value
                if isinstance(filler, ThingClass) and get_label(filler) == "IMTS Registration":
                    new_ax = obj_prop.some(target_user_class)
                    new_is_a.append(new_ax)
                    changed_here = True
                    print(f"✓ {mapping_name}: {cls_label}: IMTS Registration → {target_label}")
                else:
                    new_is_a.append(ax)
            else:
                new_is_a.append(ax)

        if changed_here:
            with onto:
                cls.is_a[:] = new_is_a
            updated += 1

    print(f"{mapping_name} restrictions updated for {updated} classes")
    return updated

# -----------------------------
# Run updates for exhibitor and visitor
# -----------------------------

if not hasattr(onto, "hasIMTSExhibitorRegistrationUser"):
    raise RuntimeError("hasIMTSExhibitorRegistrationUser not in ontology")
if not hasattr(onto, "hasIMTSVisitorRegistrationUser"):
    raise RuntimeError("hasIMTSVisitorRegistrationUser not in ontology")

exh_prop = onto.hasIMTSExhibitorRegistrationUser
vis_prop = onto.hasIMTSVisitorRegistrationUser

exh_count = update_restrictions(exh_prop, exhibitor_mapping, "Exhibitor")
vis_count = update_restrictions(vis_prop, visitor_mapping, "Visitor")

# -----------------------------
# Save ontology
# -----------------------------

onto.save(file=OUTPUT_FILE, format="rdfxml")
print(f"\nFinal ontology saved to {OUTPUT_FILE}")
print(f"Exhibitor axioms updated: {exh_count}")
print(f"Visitor axioms updated:   {vis_count}")
print(f"Total classes:            {len(list(onto.classes()))}")
