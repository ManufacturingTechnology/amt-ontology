"""
app.im_diagram
==============
Mermaid ``classDiagram`` source generator for the Information Model tab.

The IM (``im.ttl``) is a small UML-style schema: a handful of classes
(Visitor, Exhibitor, Company, IMTS, AMT, …) linked by object properties and
adorned with datatype properties + cardinality restrictions. The browser
renders this twice: once as a containment tree (``build_class_tree`` on the
IM graph) and once as a side-by-side class diagram, which is what this
module produces.

The generated string is fed directly to Mermaid in the browser. Classes
whose URI sits outside the IM namespace are emitted with a
``<<external>>`` stereotype so the diagram shows where the IM connects to
the rest of the suite (e.g. ``ProductCategory`` from pc.ttl).

Object properties without an ``rdfs:range`` are silently skipped — there is
nothing to point an arrow *at* in those cases.
"""

from __future__ import annotations

import rdflib
from rdflib.namespace import OWL, RDF, RDFS

from .labels import local_name
from .namespaces import in_im_namespace

# ---------------------------------------------------------------------------
# Restriction sweep — collects cardinalities and the set of properties
# restricted on each IM class, so callers can recover datatype properties
# whose declaration has no rdfs:domain but whose presence on a class is
# implied by an owl:Restriction (e.g. ``registrationDate`` in im.ttl).
# ---------------------------------------------------------------------------


def _collect_cardinalities(graph: rdflib.Graph) -> tuple[dict, dict]:
    """Walk every ``owl:Restriction`` reachable via ``rdfs:subClassOf``.

    Returns ``(cards, rest_props)``:

    * ``cards``       – ``{(class_local, prop_local): "min..max"}``
    * ``rest_props``  – ``{class_local: {prop_uri, ...}}`` listing every
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

    * one ``class`` block per IM class with its datatype properties (typed
      and cardinality-annotated, drawing on both ``rdfs:domain`` and
      ``owl:Restriction`` paths so domain-less declarations still appear
      under the correct class);
    * external classes referenced by object-property ranges, marked
      ``<<external>>``;
    * one association line per object property whose ``rdfs:range`` is
      declared, with the cardinality (from ``owl:Restriction``) on the
      target end.
    """
    cards, rest_props = _collect_cardinalities(graph)

    # ── Datatype-property catalogue, keyed by class local name ─────────────
    dt_uris = set(graph.subjects(RDF.type, OWL.DatatypeProperty))
    dtprops: dict = {}  # {class_local: [(name, range_local, card), ...]}

    for p in dt_uris:
        ranges = list(graph.objects(p, RDFS.range))
        rng = local_name(ranges[0]) if ranges else "string"
        for d in graph.objects(p, RDFS.domain):
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

    # ── Header + IM-internal classes ───────────────────────────────────────
    lines: list[str] = ["classDiagram", "  direction LR"]
    im_class_locals = sorted(
        {local_name(c) for c in graph.subjects(RDF.type, OWL.Class) if in_im_namespace(c)}
    )
    for c_l in im_class_locals:
        props = sorted(dtprops.get(c_l, []))
        if props:
            lines.append(f"  class {c_l} {{")
            for pname, rng, card in props:
                suffix = f" [{card}]" if card else ""
                lines.append(f"    +{pname}: {rng}{suffix}")
            lines.append("  }")
        else:
            lines.append(f"  class {c_l}")

    # ── External classes referenced by object-property ranges ──────────────
    ext: set = set()
    for p in graph.subjects(RDF.type, OWL.ObjectProperty):
        for r in graph.objects(p, RDFS.range):
            if isinstance(r, rdflib.URIRef) and not in_im_namespace(r):
                ext.add(local_name(r))
    for ec in sorted(ext):
        lines.append(f"  class {ec}")
        lines.append(f"  <<external>> {ec}")

    # ── Object-property associations; cardinality on target side ───────────
    op_lines: list[str] = []
    for p in sorted(graph.subjects(RDF.type, OWL.ObjectProperty)):
        ranges = [r for r in graph.objects(p, RDFS.range) if isinstance(r, rdflib.URIRef)]
        if not ranges:
            continue  # Unranged properties are not drawn.
        domains = [d for d in graph.objects(p, RDFS.domain) if isinstance(d, rdflib.URIRef)]
        p_l = local_name(p)
        for d in domains:
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
