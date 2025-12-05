import types
from pathlib import Path
from owlready2 import *

ONTO_IRI = "http://amt.org/ontology"
OUTPUT_FILE = "ontology/amt-ontology-draft1.owl"
MD_FILE = "resources/model.md"

# -----------------------------
# Markdown parsing: nested bullets -> tree
# -----------------------------

def parse_markdown_tree(path: str):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    nodes = []
    
    for line in lines:
        if not line.strip():
            continue
            
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.lstrip(" ")
        
        if not stripped.startswith(("-", "*", "+")):
            continue
            
        label = stripped[1:].strip()
        level = indent // 2
        nodes.append((level, label))

    root = []
    stack = []
    
    for level, label in nodes:
        node = [label, []]
        
        if not stack:
            root.append(node)
            stack.append((level, node))
            continue
            
        while stack and stack[-1][0] >= level:
            stack.pop()
            
        if not stack:
            root.append(node)
        else:
            parent_node = stack[-1][1]
            parent_node[1].append(node)
            
        stack.append((level, node))
        
    return root  # [ [label, [children...]], ... ]

# -----------------------------
# Single ontology with User namespace prefixing
# -----------------------------

onto = get_ontology(ONTO_IRI)

with onto:
    # Base capability/specification properties
    class hasCapability(ObjectProperty):
        domain = [Thing]
        range = [Thing]

    class hasSpecification(ObjectProperty):
        domain = [Thing]
        range = [Thing]

    # Mirror properties for bidirectionality
    class hasUser(ObjectProperty):
        domain = [Thing]
        range = [Thing]

    class uses(ObjectProperty):
        domain = [Thing]
        range = [Thing]
        inverse_property = hasUser

    # IMTS Registration sub-property hierarchy
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
# Helper functions
# -----------------------------

class_cache = {}

def make_safe_name(label: str) -> str:
    import re
    parts = re.split(r"[^0-9A-Za-z]+", label.strip())
    parts = [p for p in parts if p]
    
    if not parts:
        parts = ["Anonymous"]
        
    camel = "".join(p[0].upper() + p[1:] for p in parts)
    
    if camel[0].isdigit():
        camel = "C_" + camel
        
    return camel

def get_or_create_class(raw_label: str, parent, use_user_ns: bool):
    display_label = raw_label.strip()
    key = (display_label, use_user_ns)
    
    if key in class_cache:
        return class_cache[key]

    safe_name = make_safe_name(display_label)
    
    # Add User_ prefix for classes in user namespace
    if use_user_ns:
        safe_name = f"User_{safe_name}"
    
    with onto:
        NewClass = types.new_class(safe_name, (parent,))
        
    NewClass.label = [display_label]
    class_cache[key] = NewClass
    return NewClass

def process_md_tree(tree, parent, in_user_ns: bool):
    for raw_label, children in tree:
        display_label = raw_label.strip()
        
        # Switch to user namespace at "User" class and stay there
        use_user_ns = in_user_ns or (display_label == "User")
        
        cls = get_or_create_class(raw_label, parent, use_user_ns)
        
        # Recurse with updated namespace state
        if children:
            process_md_tree(children, cls, use_user_ns)

# -----------------------------
# Build and save ontology
# -----------------------------

print("Parsing Markdown tree...")
md_tree = parse_markdown_tree(MD_FILE)

print("Processing class hierarchy...")
process_md_tree(md_tree, Thing, in_user_ns=False)

print(f"Saving ontology to {OUTPUT_FILE}...")
onto.save(file=OUTPUT_FILE, format="rdfxml")

total_classes = len(list(onto.classes()))
print(f"Ontology saved to {OUTPUT_FILE}")
print("User classes have 'User_' prefix with proper hierarchy")
print("Check Protégé Classes tab for correct tree structure")
print(f"Total classes created: {total_classes}")
