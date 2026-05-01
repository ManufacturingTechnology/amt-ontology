import types, re
from pathlib import Path
from owlready2 import *

BASE_IRI = "http://ontology.amt.org/product-categories#"
VERSION_IRI = "http://ontology.amt.org/product-categories/v1.0.0#" # To be manually set in the output file after generation
OUTPUT_FILE = "ontology/product-categories-v1.owl"
MD_FILE = "resources/model.md"

# -----------------------------
# Markdown parsing: nested bullets -> tree
# -----------------------------

def parse_markdown_tree(path: str):
    if not Path(path).exists():
        print(f"Error: {path} not found.")
        return []
    
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
# Helper functions
# -----------------------------

onto = get_ontology(BASE_IRI)
class_cache = {}

def make_safe_name(label: str) -> str:
    """Converts label to CamelCase for valid RDF URIs."""
    parts = re.split(r"[^0-9A-Za-z]+", label.strip())
    parts = [p for p in parts if p]
    
    if not parts:
        parts = ["AnonymousClass"]
        
    camel = "".join(p[0].upper() + p[1:] for p in parts)
    
    if camel[0].isdigit():
        camel = "C_" + camel
        
    return camel

def get_or_create_class(raw_label: str, parent):
    display_label = raw_label.strip()
    
    if display_label in class_cache:
        return class_cache[display_label]

    safe_name = make_safe_name(display_label)
    
    with onto:
        NewClass = types.new_class(safe_name, (parent,))
        NewClass.label = [display_label]
        
    class_cache[display_label] = NewClass
    return NewClass

def process_md_tree(tree, parent):
    for raw_label, children in tree:
        cls = get_or_create_class(raw_label, parent)
        
        if children:
            process_md_tree(children, cls)


# -----------------------------
# Build and save ontology
# -----------------------------

if __name__ == "__main__":
    print(f"Parsing Markdown tree from {MD_FILE}...")
    md_tree = parse_markdown_tree(MD_FILE)

    print("Processing lass hierarchy...")
    process_md_tree(md_tree, Thing)

    print(f"Saving ontology to {OUTPUT_FILE}...")
    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    onto.save(file=OUTPUT_FILE, format="rdfxml")

    total_classes = len(list(onto.classes()))
    print(f"Ontology saved to {OUTPUT_FILE}")
    print(f"Total classes created: {total_classes}")
