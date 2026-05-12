"""
app.im_diagram
==============
Mermaid ``classDiagram`` source generator for the Information Model tab.

The IM (``im.ttl``) is a small UML-style schema: a handful of classes
(Visitor, Exhibitor, Company, IMTS, AMT, ...) linked by object properties
and adorned with datatype properties + cardinality restrictions. The
browser renders this twice: once as a containment tree
(``build_class_tree`` on the IM graph) and once as a side-by-side class
diagram, which is what this module produces.

The generated string is fed directly to Mermaid in the browser. The
generator emits every IM-namespace declaration the browser would
otherwise swallow:

* each ``owl:Class`` block is stamped with its most specific gUFO
  stereotype (``<<Kind>>``, ``<<Role>>``, ``<<RoleMixin>>``,
  ``<<Category>>``, ``<<EventType>>``, ...);
* each ``owl:NamedIndividual`` in the IM namespace (e.g. ``im:AMT``) is
  emitted as its own box stamped ``<<NamedIndividual>>``, with a dashed
  realisation arrow back to every class it instantiates;
* ``rdfs:subClassOf`` arcs between two IM-internal classes are drawn as
  UML generalisation edges (parent ``<|--`` child), so the
  Person/Visitor/BoothStaff and Registration/VisitorRecord/ExhibitorRecord
  hierarchies are visible at a glance;
* ``rdfs:domain`` expressed as an ``owl:unionOf`` blank node (e.g.
  ``im:name`` whose domain is ``(im:Person im:Company)``) is fanned out
  to every member class so the property appears under each.

Classes whose URI sits outside the IM namespace -- referenced by an
object property's ``rdfs:range`` -- are still emitted with a
``<<external>>`` stereotype so the diagram shows where the IM connects
to the rest of the suite (e.g. ``ProductCategory`` from pc.ttl).

Object properties without an ``rdfs:range`` are silently skipped --
there is nothing to point an arrow *at* in those cases.
"""

from __future__ import annotations

import rdflib
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS

from .labels import local_name
from .namespaces import in_im_namespace

# ---------------------------------------------------------------------------
# gUFO stereotype lookup
# ---------------------------------------------------------------------------
#
# Every IM class declares a gUFO upper-level type alongside ``owl:Class``
# (e.g. ``im:Visitor a owl:Class, gufo:Role``). We surface that as a
# Mermaid stereotype on the class block so a reader can tell Kinds from
# Roles from RoleMixins at a glance. The list is ordered
# most-specific-first: if a class somehow declares multiple gUFO types we
# display the first match.

GUFO = rdflib.Namespace("http://purl.org/nemo/gufo#")

_GUFO_STEREOTYPES: tuple[tuple[str, rdflib.URIRef], ...] = (
    ("Kind", GUFO.Kind),
    ("SubKind", GUFO.SubKind),
    ("Role", GUFO.Role),
    ("RoleMixin", GUFO.RoleMixin),
    ("Phase", GUFO.Phase),
    ("PhaseMixin", GUFO.PhaseMixin),
    ("Mixin", GUFO.Mixin),
    ("Category", GUFO.Category),
    ("EventType", GUFO.EventType),
    ("SituationType", GUFO.SituationType),
    ("Quality", GUFO.Quality),
    ("Mode", GUFO.Mode),
    ("Relator", GUFO.Relator),
)


def _gufo_stereotype(graph: rdflib.Graph, class_uri: rdflib.URIRef) -> str | None:
    """Return the most specific gUFO stereotype label for ``class_uri``."""
    types = set(graph.objects(class_uri, RDF.type))
    for label, uri in _GUFO_STEREOTYPES:
        if uri in types:
            return label
    return None


# ---------------------------------------------------------------------------
# Domain expansion -- handles owl:unionOf blank-node domains
# ---------------------------------------------------------------------------


def _expand_domains(graph: rdflib.Graph, prop: rdflib.URIRef):
    """Yield every class URI in *prop*'s ``rdfs:domain``.

    A domain can be a plain URI (the common case) or a blank node with an
    ``owl:unionOf`` list (used in ``im.ttl`` for ``im:name`` whose domain
    is ``(im:Person im:Company)``). This helper flattens both shapes.
    """
    for d in graph.objects(prop, RDFS.domain):
        if isinstance(d, rdflib.URIRef):
            yield d
            continue
        for union_list in graph.objects(d, OWL.unionOf):
            for item in Collection(graph, union_list):
                if isinstance(item, rdflib.URIRef):
                    yield item


# ---------------------------------------------------------------------------
# Restriction sweep -- collects cardinalities and the set of properties
# restricted on each IM class, so callers can recover datatype properties
# whose declaration has no rdfs:domain but whose presence on a class is
# implied by an owl:Restriction (e.g. ``registrationDate`` in im.ttl).
# ---------------------------------------------------------------------------


def _collect_cardinalities(graph: rdflib.Graph) -> tuple[dict, dict]:
    """Walk every ``owl:Restriction`` reachable via ``rdfs:subClassOf``.

    Returns ``(cards, rest_props)``:

    * ``cards``       - ``{(class_local, prop_local): "min..max"}``
    * ``rest_props``  - ``{class_local: {prop_uri, ...}}`` listing every
      property URI restricted on each IM class, regardless of which
      cardinality keywords are present.
    """
    cards: dict = {}
    rest_props: dict = {}
    for c in graph.subjects(RDF.type, OWL.Class):
        if not in_im_namespace(c):
            continue
        c_l = local_name(c)
        for r in graph.objects(c, RDFS.subClassOf):
            if (r, RDF.type, OWL.Restriction) not in graph:
                continue
            prop = next(graph.objects(r, OWL.onProperty), None)
            if not isinstance(prop, rdflib.URIRef):
                continue
            rest_props.setdefault(c_l, set()).add(prop)
            ex = next(graph.objects(r, OWL.cardinality), None)
            mn = next(graph.objects(r, OWL.minCardinality), None)
            mx = next(graph.objects(r, OWL.maxCardinality), None)
            if ex is not None:
                card = str(int(ex))
            elif mn is not None and mx is not None:
                card = f"{int(mn)}..{int(mx)}"
            elif mn is not None:
                card = f"{int(mn)}..*"
            elif mx is not None:
                card = f"0..{int(mx)}"
            else:
                continue
            cards[(c_l, local_name(prop))] = card
    return cards, rest_props


# ---------------------------------------------------------------------------
# Mermaid source generator
# ---------------------------------------------------------------------------


def generate_im_mermaid(graph: rdflib.Graph) -> str:
    """Return a Mermaid ``classDiagram`` source string for *graph*.

    The generated diagram contains:

    * one ``class`` block per IM ``owl:Class`` with its gUFO stereotype
      and its datatype properties (typed and cardinality-annotated,
      drawing on both ``rdfs:domain`` -- including ``owl:unionOf``
      blank-node domains -- and ``owl:Restriction`` paths so domain-less
      declarations still appear under the correct class);
    * one ``class`` block per IM ``owl:NamedIndividual`` stamped
      ``<<NamedIndividual>>``, with a dashed realisation arrow back to
      every IM-internal class it instantiates;
    * external classes referenced by object-property ranges, marked
      ``<<external>>``;
    * generalisation edges (``parent <|-- child``) for every
      ``rdfs:subClassOf`` between two IM-internal classes, so the class
      hierarchy is visible alongside the property structure;
    * one association line per object property whose ``rdfs:range`` is
      declared, with the cardinality (from ``owl:Restriction``) on the
      target end.
    """
    cards, rest_props = _collect_cardinalities(graph)

    # Datatype-property catalogue, keyed by class local name.
    dt_uris = set(graph.subjects(RDF.type, OWL.DatatypeProperty))
    dtprops: dict = {}  # {class_local: [(name, range_local, card), ...]}

    for p in dt_uris:
        ranges = list(graph.objects(p, RDFS.range))
        rng = local_name(ranges[0]) if ranges else "string"
        for d in _expand_domains(graph, p):
            if not in_im_namespace(d):
                continue
            d_l = local_name(d)
            card = cards.get((d_l, local_name(p)), "")
            dtprops.setdefault(d_l, []).append((local_name(p), rng, card))

    # Datatype properties without rdfs:domain but visible via restriction.
    for c_l, prop_uris in rest_props.items():
        for prop in prop_uris:
            if prop not in dt_uris:
                continue
            p_l = local_name(prop)
            if any(p[0] == p_l for p in dtprops.get(c_l, [])):
                continue
            ranges = list(graph.objects(prop, RDFS.range))
            rng = local_name(ranges[0]) if ranges else "string"
            card = cards.get((c_l, p_l), "")
            dtprops.setdefault(c_l, []).append((p_l, rng, card))

    # Header + IM-internal classes.
    lines: list[str] = ["classDiagram", "  direction LR"]

    im_classes = {
        c for c in graph.subjects(RDF.type, OWL.Class) if in_im_namespace(c)
    }
    im_class_by_local: dict = {local_name(c): c for c in im_classes}
    # Track which local names exist as boxes so we don't emit relationship
    # edges that reference an undeclared box.
    declared_locals: set = set(im_class_by_local)

    for c_l in sorted(im_class_by_local):
        c = im_class_by_local[c_l]
        props = sorted(dtprops.get(c_l, []))
        if props:
            lines.append(f"  class {c_l} {{")
            for pname, rng, card in props:
                suffix = f" [{card}]" if card else ""
                lines.append(f"    +{pname}: {rng}{suffix}")
            lines.append("  }")
        else:
            lines.append(f"  class {c_l}")
        stereo = _gufo_stereotype(graph, c)
        if stereo:
            lines.append(f"  <<{stereo}>> {c_l}")

    # Named individuals declared in the IM namespace.
    im_individuals = sorted(
        {
            i
            for i in graph.subjects(RDF.type, OWL.NamedIndividual)
            if in_im_namespace(i)
        },
        key=local_name,
    )
    for ind in im_individuals:
        i_l = local_name(ind)
        declared_locals.add(i_l)
        lines.append(f"  class {i_l}")
        lines.append(f"  <<NamedIndividual>> {i_l}")

    # External classes referenced by object-property ranges.
    ext: set = set()
    for p in graph.subjects(RDF.type, OWL.ObjectProperty):
        for r in graph.objects(p, RDFS.range):
            if isinstance(r, rdflib.URIRef) and not in_im_namespace(r):
                ext.add(local_name(r))
    for ec in sorted(ext):
        lines.append(f"  class {ec}")
        lines.append(f"  <<external>> {ec}")
        declared_locals.add(ec)

    # Subclass relationships (IM-internal only). parent <|-- child renders
    # a UML generalisation arrow with the arrowhead at the parent end.
    # Restrictions are blank nodes, hence the URIRef check.
    sub_edges: set = set()
    for c, sup in graph.subject_objects(RDFS.subClassOf):
        if not in_im_namespace(c):
            continue
        if not isinstance(sup, rdflib.URIRef):
            continue
        if not in_im_namespace(sup):
            continue
        sub_edges.add((local_name(sup), local_name(c)))
    for parent_l, child_l in sorted(sub_edges):
        if parent_l not in declared_locals or child_l not in declared_locals:
            continue
        lines.append(f"  {parent_l} <|-- {child_l}")

    # NamedIndividual -> class typing. Mermaid's ``..|>`` is realisation
    # (dashed, hollow arrow). We re-use it to express OWL instantiation:
    # a NamedIndividual realises its class.
    for ind in im_individuals:
        i_l = local_name(ind)
        for t in graph.objects(ind, RDF.type):
            if t == OWL.NamedIndividual:
                continue
            if not isinstance(t, rdflib.URIRef):
                continue
            if not in_im_namespace(t):
                continue
            t_l = local_name(t)
            if t_l not in declared_locals:
                continue
            lines.append(f"  {i_l} ..|> {t_l} : instanceOf")

    # Object-property associations; cardinality on the target side.
    op_lines: list = []
    for p in sorted(graph.subjects(RDF.type, OWL.ObjectProperty)):
        ranges = [r for r in graph.objects(p, RDFS.range) if isinstance(r, rdflib.URIRef)]
        if not ranges:
            continue  # Unranged properties are not drawn.
        p_l = local_name(p)
        for d in _expand_domains(graph, p):
            if not isinstance(d, rdflib.URIRef):
                continue
            d_l = local_name(d)
            for r in ranges:
                r_l = local_name(r)
                card = cards.get((d_l, p_l), "")
                if card:
                    op_lines.append(f'  {d_l} --> "{card}" {r_l} : {p_l}')
                else:
                    op_lines.append(f"  {d_l} --> {r_l} : {p_l}")
    lines.extend(op_lines)

    return "\n".join(lines)
