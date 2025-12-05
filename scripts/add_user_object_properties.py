import json
from owlready2 import *

INPUT_FILE = "ontology/amt-ontology-draft1.owl"
OUTPUT_FILE = "ontology/amt-ontology-draft2.owl"
JSON_FILE = "resources/model.json"

# -----------------------------
# Load existing ontology and JSON
# -----------------------------

# Load existing local ontology file directly
onto = get_ontology(INPUT_FILE).load()

# Load JSON and flatten nested types recursively
def flatten_types(nested_types):
    """Recursively flatten nested 'types' dict to get all type names"""
    flat_types = {}
    def recurse(types_dict):
        for type_name, type_info in types_dict.items():
            flat_types[type_name] = type_info
            if "types" in type_info:
                recurse(type_info["types"])
    recurse(nested_types)
    return flat_types

with open(JSON_FILE, "r", encoding="utf-8") as f:
    json_data = json.load(f)
json_types = flatten_types(json_data.get("types", {}))

# -----------------------------
# Ensure IMTSRegistration class exists as User_IMTSRegistration
# -----------------------------

with onto:
    # IMTSRegistration is now User_IMTSRegistration (subclass of User)
    if not hasattr(onto, "User_IMTSRegistration"):
        # Find User class first
        User = next((cls for cls in onto.classes() if "User" in [lbl for lbl in cls.label]), None)
        if User:
            class User_IMTSRegistration(User):
                pass
        else:
            # Fallback: create under Thing if User not found
            class User_IMTSRegistration(Thing):
                pass

# -----------------------------
# Ensure required properties exist
# -----------------------------

with onto:
    if not hasattr(onto, "hasUser"):
        class hasUser(ObjectProperty):
            domain = [Thing]
            range = [Thing]

        class uses(ObjectProperty):
            domain = [Thing]
            range = [Thing]
            inverse_property = hasUser

        class hasIMTSRegistrationUser(hasUser):
            pass

        class IMTSRegistrationUses(uses):
            pass

        class hasIMTSExhibitorRegistrationUser(hasIMTSRegistrationUser):
            pass

        class hasIMTSVisitorRegistrationUser(hasIMTSRegistrationUser):
            pass

        class IMTSExhibitorRegistrationUses(IMTSRegistrationUses):
            pass

        class IMTSVisitorRegistrationUses(IMTSRegistrationUses):
            pass

# -----------------------------
# Helpers - Updated for User_ prefixed classes
# -----------------------------

def get_class_by_label(label: str):
    """Find class by label in loaded ontology (handles User_ prefixed classes)"""
    for cls in onto.classes():
        if cls.label and any(label == lbl for lbl in cls.label):
            return cls
    return None

# -----------------------------
# Add JSON-driven restrictions to existing classes ONLY
# -----------------------------

print("Processing JSON types and adding restrictions...")
processed = 0
exhibitor_added = 0
visitor_added = 0

for class_label, type_info in json_types.items():
    cls = get_class_by_label(class_label)
    if cls:
        print(f"Found class '{class_label}' -> {cls}")
        
        with onto:
            if type_info.get("is_exhibitor_category"):
                restriction = onto.hasIMTSExhibitorRegistrationUser.some(onto.User_IMTSRegistration)
                if restriction not in cls.is_a:
                    cls.is_a.append(restriction)
                    print(f"   Added hasIMTSExhibitorRegistrationUser -> User_IMTSRegistration")
                    exhibitor_added += 1
            
            if type_info.get("is_visitor_category"):
                restriction = onto.hasIMTSVisitorRegistrationUser.some(onto.User_IMTSRegistration)
                if restriction not in cls.is_a:
                    cls.is_a.append(restriction)
                    print(f"   Added hasIMTSVisitorRegistrationUser -> User_IMTSRegistration")
                    visitor_added += 1
        
        processed += 1
    else:
        print(f"Class '{class_label}' not found in ontology")

# -----------------------------
# Save updated ontology
# -----------------------------

onto.save(file=OUTPUT_FILE, format="rdfxml")
print(f"\nUpdated ontology saved to {OUTPUT_FILE}")
print(f"Processed {processed}/{len(json_types)} JSON types (including nested)")
print(f"Added {exhibitor_added} exhibitor restrictions")
print(f"Added {visitor_added} visitor restrictions")
print("IMTSRegistration updated to User_IMTSRegistration (subclass of User)")
