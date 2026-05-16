"""
app.namespaces
==============
RDF namespaces and common URI constants used across the application.

The four AMT-owned namespaces:

* ``pc``       - ``http://ontology.amt.org/product-categories#``
* ``ind``      - ``http://ontology.amt.org/industries#``
* ``im``       - ``http://ontology.amt.org/im#``
* ``amtmeta``  - ``http://ontology.amt.org/meta#``

The two ontology-IRI constants (``PC_ONTOLOGY_IRI``, ``IND_ONTOLOGY_IRI``)
are the *ontology IRIs* (no trailing ``#``) used as the object of
``amtmeta:viewOf`` declarations in the view files.
"""

import rdflib

# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------

NS_PC = rdflib.Namespace("http://ontology.amt.org/product-categories#")
NS_IND = rdflib.Namespace("http://ontology.amt.org/industries#")
NS_IM = rdflib.Namespace("http://ontology.amt.org/im#")
NS_AMTMETA = rdflib.Namespace("http://ontology.amt.org/meta#")

# ---------------------------------------------------------------------------
# amtmeta vocabulary atoms (pre-bound for terseness in callers)
# ---------------------------------------------------------------------------

AMTMETA_COLLECTION = NS_AMTMETA.Collection
AMTMETA_GROUPS = NS_AMTMETA.groups
AMTMETA_VIEWOF = NS_AMTMETA.viewOf

# ---------------------------------------------------------------------------
# Ontology-IRI constants (objects of amtmeta:viewOf in the view files)
# ---------------------------------------------------------------------------

PC_ONTOLOGY_IRI = rdflib.URIRef("http://ontology.amt.org/product-categories")
IND_ONTOLOGY_IRI = rdflib.URIRef("http://ontology.amt.org/industries")
IM_ONTOLOGY_IRI = rdflib.URIRef("http://ontology.amt.org/im")

# Base URI string for the IM namespace, used by :mod:`app.im_cytoscape`
# to distinguish IM-internal classes from external classes referenced by
# object-property ranges.
IM_BASE_NS = "http://ontology.amt.org/im#"


def in_im_namespace(uri) -> bool:
    """True iff ``uri`` is an rdflib URI inside the IM namespace."""
    return isinstance(uri, rdflib.URIRef) and str(uri).startswith(IM_BASE_NS)
