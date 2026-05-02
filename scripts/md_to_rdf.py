"""
md_to_rdf.py
============
Convert a nested Markdown bullet-list into an OWL class hierarchy and persist
it as an RDF/XML ontology file.

The Markdown file is expected to use standard list markers (``-``, ``*``, or
``+``) with two-space indentation per hierarchy level.  Each list item becomes
an OWL class whose ``rdfs:label`` is the item text and whose parent class is
determined by the indentation depth.

Output
------
The ontology is serialised to ``ontology/product-categories-v1.owl`` in
RDF/XML format using the base IRI ``http://ontology.amt.org/product-categories#``.

Usage
-----
    python md_to_rdf.py
"""

import re
import types
from pathlib import Path

from owlready2 import Thing, get_ontology

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_IRI = "http://ontology.amt.org/product-categories#"
OUTPUT_FILE = "ontology/product-categories-v1.owl"
MD_FILE = "resources/model.md"

# ---------------------------------------------------------------------------
# Ontology initialisation
# ---------------------------------------------------------------------------

onto = get_ontology(BASE_IRI)

# Maps display label → owlready2 class to prevent duplicate class creation
_class_cache: dict[str, type] = {}

# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------


def parse_markdown_tree(path: str) -> list:
    """
    Parse a nested Markdown bullet list into a tree of ``[label, children]``
    nodes.

    Only lines beginning with ``-``, ``*``, or ``+`` (after optional leading
    spaces) are processed; blank lines and non-list lines are ignored.
    Indentation depth is calculated as ``leading_spaces // 2``.

    Parameters
    ----------
    path : str
        File-system path to the Markdown source file.

    Returns
    -------
    list
        A list of root nodes, where each node is ``[label: str, children: list]``.
        Returns an empty list when the file does not exist.
    """
    source = Path(path)
    if not source.exists():
        print(f"Error: Markdown file not found: {path}")
        return []

    nodes: list[tuple[int, str]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip(" ")
        if not stripped or not stripped[0] in "-*+":
            continue
        level = (len(line) - len(stripped)) // 2
        label = stripped[1:].strip()
        nodes.append((level, label))

    # Build tree from the flat (level, label) sequence
    root: list = []
    stack: list[tuple[int, list]] = []  # (level, node)

    for level, label in nodes:
        node = [label, []]

        # Pop stack entries that are not ancestors of this node
        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            stack[-1][1][1].append(node)  # append to parent's children list
        else:
            root.append(node)

        stack.append((level, node))

    return root


# ---------------------------------------------------------------------------
# OWL class creation
# ---------------------------------------------------------------------------


def _make_safe_name(label: str) -> str:
    """
    Convert a human-readable label to a CamelCase OWL class name suitable for
    use in an IRI fragment.

    Non-alphanumeric character runs are used as word delimiters.  A numeric
    first character is prefixed with ``C_`` to satisfy OWL naming constraints.

    Parameters
    ----------
    label : str
        Raw label text, e.g. ``"3D Printing & Additive Mfg"``.

    Returns
    -------
    str
        CamelCase name, e.g. ``"C_3DPrintingAdditiveMfg"``.
    """
    parts = [p for p in re.split(r"[^0-9A-Za-z]+", label.strip()) if p]
    if not parts:
        parts = ["AnonymousClass"]
    camel = "".join(p[0].upper() + p[1:] for p in parts)
    if camel[0].isdigit():
        camel = "C_" + camel
    return camel


def get_or_create_class(label: str, parent: type) -> type:
    """
    Return the existing owlready2 class for *label*, or create a new one as a
    subclass of *parent*.

    Parameters
    ----------
    label : str
        Human-readable display label (stored as ``rdfs:label``).
    parent : type
        Owlready2 superclass (e.g. ``Thing`` or another ontology class).

    Returns
    -------
    type
        The owlready2 class object.
    """
    display_label = label.strip()
    if display_label in _class_cache:
        return _class_cache[display_label]

    with onto:
        new_cls = types.new_class(_make_safe_name(display_label), (parent,))
        new_cls.label = [display_label]

    _class_cache[display_label] = new_cls
    return new_cls


def process_md_tree(tree: list, parent: type) -> None:
    """
    Recursively walk the parsed Markdown tree and create owlready2 classes.

    Parameters
    ----------
    tree : list
        List of ``[label, children]`` nodes (output of :func:`parse_markdown_tree`
        or a subtree thereof).
    parent : type
        Owlready2 class to use as the superclass for all nodes at this level.
    """
    for label, children in tree:
        cls = get_or_create_class(label, parent)
        if children:
            process_md_tree(children, cls)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Parsing Markdown tree from {MD_FILE}...")
    md_tree = parse_markdown_tree(MD_FILE)

    print("Building OWL class hierarchy...")
    process_md_tree(md_tree, Thing)

    output_path = Path(OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Saving ontology to {OUTPUT_FILE}...")
    onto.save(file=OUTPUT_FILE, format="rdfxml")

    total_classes = len(list(onto.classes()))
    print(f"Done. Total classes created: {total_classes}")