"""
tests.test_semantic_invariants
==============================
Semantic / structural invariants that the AMT ontology design implies but
that no other test enforces. These run against the union of every authored
TTL (modulo per-file headers) and catch a class of mistakes that would
otherwise propagate downstream — UFO Kind-partition violations, dangling
restriction references, version-bumps that miss the gitTag, dead prefix
declarations, etc.

Grouped by concern:

    Foundational UFO invariants
        - TestUFOKindPartition       — every domain individual has exactly
                                       one gufo:Kind via transitive subClassOf
        - TestRoleAncestry           — every gufo:Role has a Kind ancestor
        - TestSubKindAncestry        — every gufo:SubKind has a Kind ancestor
        - TestDisjointnessSanity     — no individual instantiates two
                                       members of any owl:AllDisjointClasses

    OMG Commons invariants
        - TestCommonsClassifierScoping  — every Classifier has exactly one
                                          isDefinedIn → ClassificationScheme

    Restriction / property hygiene
        - TestRestrictionSanity              — onProperty / onClass references
                                               resolve to declared entities
        - TestNamedIndividualHygiene         — no dangling NamedIndividuals
        - TestObjectPropertyRangeHygiene     — no literal values for
                                               ObjectProperties

    Release / governance hygiene
        - TestVersionCoherence       — versionInfo, versionIRI, gitTag agree
        - TestMetadataCompleteness   — required amtmeta:* fields present
        - TestStatusValuesCanonical  — status / approvalStatus values are
                                       from the four canonical individuals

    File-level hygiene
        - TestPrefixHygiene          — every @prefix declared is used

The tests run against the authored TTL files only — they do not follow
``owl:imports`` into gufo / Commons. External URIs (anything outside the
AMT root) are treated as opaquely-declared and accepted without further
verification; the imported ontologies are assumed to be well-formed on
their own terms.
"""

from __future__ import annotations

import re
import unittest

import rdflib
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS

from app.namespaces import NS_AMTMETA
from app.paths import ONTOLOGY_DIR

# ---------------------------------------------------------------------------
# External namespaces used by these tests
# ---------------------------------------------------------------------------

GUFO = rdflib.Namespace("http://purl.org/nemo/gufo#")
CMNS_CLS = rdflib.Namespace("https://www.omg.org/spec/Commons/Classifiers/")

AMT_PREFIX = "http://ontology.amt.org/"

# Canonical amtmeta:Status individuals (declared in amtmeta.ttl). Any
# value of amtmeta:status / amtmeta:approvalStatus must be one of these.
CANONICAL_STATUS = {
    NS_AMTMETA.Active,
    NS_AMTMETA.Draft,
    NS_AMTMETA.UnderReview,
    NS_AMTMETA.Deprecated,
}

# Required on every authored ontology header (governance hygiene).
REQUIRED_METADATA = (
    NS_AMTMETA.releaseDate,
    NS_AMTMETA.releaseOwner,
    NS_AMTMETA.approvalStatus,
    NS_AMTMETA.scopeSummary,
)

# Additionally required on ontologies typed as one of these vocabulary
# variants. amtmeta.ttl itself is plain owl:Ontology and does not need
# amtmeta:status.
REQUIRED_METADATA_VOCAB = (NS_AMTMETA.status,)
VOCAB_TYPES = {
    NS_AMTMETA.Taxonomy,
    NS_AMTMETA.UserView,
    NS_AMTMETA.InformationModel,
}

# Prefixes whose absence-from-body is acceptable. rdf: is implicitly used
# whenever the Turtle ``a`` shorthand appears.
SKIP_UNUSED_PREFIX = {"rdf"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_amt_internal(uri) -> bool:
    return isinstance(uri, rdflib.URIRef) and str(uri).startswith(AMT_PREFIX)


def _union_source_graph() -> rdflib.Graph:
    """Union every authored TTL into one graph. No owl:imports following —
    external (gufo, Commons) classes/properties are not materialized here."""
    g = rdflib.Graph()
    for ttl in sorted(ONTOLOGY_DIR.glob("*.ttl")):
        g.parse(ttl.as_posix(), format="turtle")
    return g


def _all_kinds(g: rdflib.Graph) -> set:
    """All classes meta-typed as gufo:Kind."""
    return {c for c in g.subjects(RDF.type, GUFO.Kind) if isinstance(c, rdflib.URIRef)}


def _transitive_ancestors(g: rdflib.Graph, cls: rdflib.URIRef) -> set:
    """All super-classes of *cls* (including itself), via rdfs:subClassOf+."""
    out: set = set()
    for ancestor in g.transitive_objects(cls, RDFS.subClassOf):
        if isinstance(ancestor, rdflib.URIRef):
            out.add(ancestor)
    return out


def _types_of(g: rdflib.Graph, ind: rdflib.URIRef) -> set:
    """rdf:type values of an individual (URIRef objects only)."""
    return {t for t in g.objects(ind, RDF.type) if isinstance(t, rdflib.URIRef)}


def _all_disjoint_groups(g: rdflib.Graph) -> list[set]:
    """Each owl:AllDisjointClasses node expanded to its member-set."""
    groups: list[set] = []
    for disjoint in g.subjects(RDF.type, OWL.AllDisjointClasses):
        for member_list in g.objects(disjoint, OWL.members):
            members: set = set()
            try:
                for m in Collection(g, member_list):
                    if isinstance(m, rdflib.URIRef):
                        members.add(m)
            except Exception:
                continue
            if members:
                groups.append(members)
    return groups


# ---------------------------------------------------------------------------
# Foundational UFO invariants
# ---------------------------------------------------------------------------


class TestUFOKindPartition(unittest.TestCase):
    """UFO requires every individual to instantiate exactly one Kind. The
    test walks every owl:NamedIndividual under the AMT root, skips meta-
    individuals (Collection, Status, Classifier, ClassificationScheme —
    these are vocabulary primitives, not domain Endurants), and asserts
    that the remaining domain individuals each transitively instantiate
    exactly one gufo:Kind class."""

    META_INDIVIDUAL_TYPES = {
        NS_AMTMETA.Collection,
        NS_AMTMETA.Status,
        CMNS_CLS.Classifier,
        CMNS_CLS.ClassificationScheme,
    }

    @classmethod
    def setUpClass(cls):
        cls.g = _union_source_graph()
        cls.kinds = _all_kinds(cls.g)

    def test_every_domain_individual_has_exactly_one_kind(self):
        offenders: list = []
        for ind in self.g.subjects(RDF.type, OWL.NamedIndividual):
            if not _is_amt_internal(ind):
                continue
            types = _types_of(self.g, ind)
            if types & self.META_INDIVIDUAL_TYPES:
                # Meta-individual (vocabulary primitive) — UFO Kind
                # partition does not apply.
                continue
            # Walk every direct type up its subClassOf chain; intersect
            # the cumulative ancestor set with the set of declared Kinds.
            ancestors: set = set()
            for t in types:
                ancestors |= _transitive_ancestors(self.g, t)
            kinds_hit = ancestors & self.kinds
            if len(kinds_hit) != 1:
                offenders.append((ind, sorted(kinds_hit)))
        self.assertFalse(
            offenders,
            f"{len(offenders)} domain individual(s) violate UFO uniqueness-"
            f"of-Kind:\n  " + "\n  ".join(f"{ind} → kinds={k}" for ind, k in offenders[:10]),
        )


class TestRoleAncestry(unittest.TestCase):
    """gufo:Role classes are anti-rigid sortals — they classify the
    instances of some rigid Kind. Each Role must therefore subClassOf
    (transitively) a gufo:Kind."""

    @classmethod
    def setUpClass(cls):
        cls.g = _union_source_graph()
        cls.kinds = _all_kinds(cls.g)

    def test_every_role_has_a_kind_ancestor(self):
        orphans: list = []
        for role in self.g.subjects(RDF.type, GUFO.Role):
            if not _is_amt_internal(role):
                continue
            if not (_transitive_ancestors(self.g, role) & self.kinds):
                orphans.append(role)
        self.assertFalse(
            orphans,
            f"{len(orphans)} gufo:Role class(es) without a Kind ancestor:\n  "
            + "\n  ".join(str(o) for o in orphans),
        )


class TestSubKindAncestry(unittest.TestCase):
    """gufo:SubKind classes specialize an identity-supplying Kind. Each
    SubKind must therefore subClassOf (transitively) a gufo:Kind."""

    @classmethod
    def setUpClass(cls):
        cls.g = _union_source_graph()
        cls.kinds = _all_kinds(cls.g)

    def test_every_subkind_has_a_kind_ancestor(self):
        orphans: list = []
        for sk in self.g.subjects(RDF.type, GUFO.SubKind):
            if not _is_amt_internal(sk):
                continue
            if not (_transitive_ancestors(self.g, sk) & self.kinds):
                orphans.append(sk)
        self.assertFalse(
            orphans,
            f"{len(orphans)} gufo:SubKind class(es) without a Kind ancestor:\n  "
            + "\n  ".join(str(o) for o in orphans),
        )


class TestDisjointnessSanity(unittest.TestCase):
    """For each owl:AllDisjointClasses block, no AMT-internal individual
    may transitively instantiate more than one member class. Belt-and-
    braces backup for the declared disjointness — catches a typo'd
    rdf:type before HermiT does."""

    @classmethod
    def setUpClass(cls):
        cls.g = _union_source_graph()
        cls.groups = _all_disjoint_groups(cls.g)

    def test_no_individual_in_multiple_disjoint_members(self):
        violations: list = []
        for ind in self.g.subjects(RDF.type, OWL.NamedIndividual):
            if not _is_amt_internal(ind):
                continue
            ancestors: set = set()
            for t in _types_of(self.g, ind):
                ancestors |= _transitive_ancestors(self.g, t)
            for members in self.groups:
                hit = ancestors & members
                if len(hit) > 1:
                    violations.append((ind, sorted(hit)))
        self.assertFalse(
            violations,
            f"{len(violations)} individual(s) instantiate >=2 pairwise-"
            f"disjoint classes:\n  "
            + "\n  ".join(f"{ind} → {hit}" for ind, hit in violations[:10]),
        )


# ---------------------------------------------------------------------------
# OMG Commons invariants
# ---------------------------------------------------------------------------


class TestCommonsClassifierScoping(unittest.TestCase):
    """Every cmns-cls:Classifier instance must have exactly one
    cmns-cls:isDefinedIn target, and that target must itself be a
    cmns-cls:ClassificationScheme. The Commons spec (Classifier class
    expression: ``∀ isDefinedIn.ClassificationScheme``) requires the
    second; the cardinality is enforced here by the test because OWL
    has no native way to express "exactly one isDefinedIn" without
    pulling the assertion into SHACL."""

    @classmethod
    def setUpClass(cls):
        cls.g = _union_source_graph()
        cls.schemes = set(cls.g.subjects(RDF.type, CMNS_CLS.ClassificationScheme))

    def test_classifiers_are_scoped_to_exactly_one_scheme(self):
        bad_count: list = []
        bad_target: list = []
        for classifier in self.g.subjects(RDF.type, CMNS_CLS.Classifier):
            if not _is_amt_internal(classifier):
                continue
            scope_vals = list(self.g.objects(classifier, CMNS_CLS.isDefinedIn))
            if len(scope_vals) != 1:
                bad_count.append((classifier, scope_vals))
                continue
            if scope_vals[0] not in self.schemes:
                bad_target.append((classifier, scope_vals[0]))
        self.assertFalse(
            bad_count,
            f"{len(bad_count)} classifier(s) with non-singleton isDefinedIn:\n  "
            + "\n  ".join(f"{c} → {vals}" for c, vals in bad_count[:10]),
        )
        self.assertFalse(
            bad_target,
            f"{len(bad_target)} classifier(s) scoped to a non-Scheme:\n  "
            + "\n  ".join(f"{c} → {t}" for c, t in bad_target[:10]),
        )


# ---------------------------------------------------------------------------
# Restriction / property hygiene
# ---------------------------------------------------------------------------


class TestRestrictionSanity(unittest.TestCase):
    """Every owl:Restriction's onProperty / onClass references must resolve
    to a declared entity *for AMT-internal URIs*. External URIs (gufo,
    Commons) are accepted as-is since they're defined in imported
    ontologies that this test does not load."""

    @classmethod
    def setUpClass(cls):
        cls.g = _union_source_graph()
        cls.declared_props = set()
        for prop_type in (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty):
            cls.declared_props |= {
                p for p in cls.g.subjects(RDF.type, prop_type) if isinstance(p, rdflib.URIRef)
            }
        cls.declared_classes = {
            c for c in cls.g.subjects(RDF.type, OWL.Class) if isinstance(c, rdflib.URIRef)
        }

    def test_restriction_targets_resolve(self):
        bad: list = []
        for r in self.g.subjects(RDF.type, OWL.Restriction):
            for prop in self.g.objects(r, OWL.onProperty):
                if _is_amt_internal(prop) and prop not in self.declared_props:
                    bad.append(("onProperty", r, prop))
            for cls in self.g.objects(r, OWL.onClass):
                if _is_amt_internal(cls) and cls not in self.declared_classes:
                    bad.append(("onClass", r, cls))
        self.assertFalse(
            bad,
            f"{len(bad)} unresolved restriction reference(s):\n  "
            + "\n  ".join(f"{k} on {r}: {ref}" for k, r, ref in bad[:10]),
        )


class TestNamedIndividualHygiene(unittest.TestCase):
    """Every AMT-internal owl:NamedIndividual must carry at least one
    rdf:type beyond owl:NamedIndividual itself. A dangling NamedIndividual
    is almost certainly a forgotten typing."""

    @classmethod
    def setUpClass(cls):
        cls.g = _union_source_graph()

    def test_named_individuals_have_a_domain_type(self):
        dangling: list = []
        for ind in self.g.subjects(RDF.type, OWL.NamedIndividual):
            if not _is_amt_internal(ind):
                continue
            types = set(self.g.objects(ind, RDF.type)) - {OWL.NamedIndividual}
            if not types:
                dangling.append(ind)
        self.assertFalse(
            dangling,
            f"{len(dangling)} dangling NamedIndividual(s) without a domain "
            f"typing:\n  " + "\n  ".join(str(i) for i in dangling),
        )


class TestObjectPropertyRangeHygiene(unittest.TestCase):
    """Triples using an owl:ObjectProperty must have non-literal objects.
    An ObjectProperty whose value is a literal is almost always a
    DatatypeProperty / ObjectProperty mix-up."""

    @classmethod
    def setUpClass(cls):
        cls.g = _union_source_graph()

    def test_object_properties_have_non_literal_objects(self):
        offenders: list = []
        object_props = {
            p for p in self.g.subjects(RDF.type, OWL.ObjectProperty) if isinstance(p, rdflib.URIRef)
        }
        for prop in object_props:
            for s, _, o in self.g.triples((None, prop, None)):
                if isinstance(o, rdflib.Literal):
                    offenders.append((s, prop, o))
        self.assertFalse(
            offenders,
            f"{len(offenders)} object-property triple(s) with literal "
            f"object:\n  " + "\n  ".join(f"{s} {p} {o!r}" for s, p, o in offenders[:10]),
        )


# ---------------------------------------------------------------------------
# Release / governance hygiene
# ---------------------------------------------------------------------------


class TestVersionCoherence(unittest.TestCase):
    """For each authored TTL, owl:versionInfo "X.Y.Z" must imply
    owl:versionIRI ending with "/X.Y.Z" and amtmeta:gitTag equal to
    "vX.Y.Z". Catches release-bumps that miss one of the three fields."""

    def test_per_file_version_fields_agree(self):
        bad: list = []
        for ttl in sorted(ONTOLOGY_DIR.glob("*.ttl")):
            g = rdflib.Graph().parse(ttl.as_posix(), format="turtle")
            for iri in g.subjects(RDF.type, OWL.Ontology):
                version = next(iter(g.objects(iri, OWL.versionInfo)), None)
                if version is None:
                    continue
                version_str = str(version)
                version_iri = next(iter(g.objects(iri, OWL.versionIRI)), None)
                git_tag = next(iter(g.objects(iri, NS_AMTMETA.gitTag)), None)
                if version_iri is not None and not str(version_iri).endswith(f"/{version_str}"):
                    bad.append(
                        (ttl.stem, "versionIRI", f"ending-with /{version_str}", str(version_iri))
                    )
                if git_tag is not None and str(git_tag) != f"v{version_str}":
                    bad.append((ttl.stem, "gitTag", f"v{version_str}", str(git_tag)))
        self.assertFalse(
            bad,
            f"{len(bad)} version-field disagreement(s):\n  "
            + "\n  ".join(
                f"{f}: {field} expected {exp}, got {act!r}" for f, field, exp, act in bad
            ),
        )


class TestMetadataCompleteness(unittest.TestCase):
    """Every authored ontology must declare the baseline governance
    metadata: releaseDate, releaseOwner, approvalStatus, scopeSummary.
    Vocabularies (Taxonomy / UserView / InformationModel) additionally
    require amtmeta:status."""

    def test_required_metadata_present(self):
        missing: list = []
        for ttl in sorted(ONTOLOGY_DIR.glob("*.ttl")):
            g = rdflib.Graph().parse(ttl.as_posix(), format="turtle")
            for iri in g.subjects(RDF.type, OWL.Ontology):
                required = list(REQUIRED_METADATA)
                if set(g.objects(iri, RDF.type)) & VOCAB_TYPES:
                    required += list(REQUIRED_METADATA_VOCAB)
                for prop in required:
                    if not list(g.objects(iri, prop)):
                        missing.append((ttl.stem, prop))
        self.assertFalse(
            missing,
            f"{len(missing)} required metadata field(s) missing:\n  "
            + "\n  ".join(f"{f}: {p}" for f, p in missing),
        )


class TestStatusValuesCanonical(unittest.TestCase):
    """Every amtmeta:status and amtmeta:approvalStatus value must be one
    of the four canonical Status individuals
    (Active / Draft / UnderReview / Deprecated). Catches typo'd value
    like amtmeta:Approved or a Literal where an IRI was expected."""

    @classmethod
    def setUpClass(cls):
        cls.g = _union_source_graph()

    def test_status_values_are_canonical(self):
        bad: list = []
        for prop in (NS_AMTMETA.status, NS_AMTMETA.approvalStatus):
            for s, _, o in self.g.triples((None, prop, None)):
                if isinstance(o, rdflib.Literal):
                    bad.append((s, prop, f"literal {o!r}"))
                elif isinstance(o, rdflib.URIRef) and o not in CANONICAL_STATUS:
                    bad.append((s, prop, str(o)))
        self.assertFalse(
            bad,
            f"{len(bad)} non-canonical status value(s):\n  "
            + "\n  ".join(f"{s} {p} {desc}" for s, p, desc in bad[:10]),
        )


# ---------------------------------------------------------------------------
# File-level hygiene
# ---------------------------------------------------------------------------


class TestPrefixHygiene(unittest.TestCase):
    """Every @prefix declaration in a TTL file should appear in that
    file's body (excluding the @prefix block itself). Unused prefix
    declarations are dead imports — either remove them or use them.

    rdf: is exempted because Turtle's ``a`` shorthand silently expands
    to rdf:type."""

    PREFIX_RE = re.compile(r"@prefix\s+([\w-]+):\s+<[^>]+>\s*\.")

    def test_all_declared_prefixes_are_used(self):
        unused: list = []
        for ttl in sorted(ONTOLOGY_DIR.glob("*.ttl")):
            text = ttl.read_text(encoding="utf-8")
            body = "\n".join(
                line for line in text.split("\n") if not line.strip().startswith("@prefix")
            )
            for prefix in self.PREFIX_RE.findall(text):
                if prefix in SKIP_UNUSED_PREFIX:
                    continue
                # Match "prefix:" followed by a non-whitespace character —
                # the regex \S excludes the @prefix line and any stray
                # whitespace cases.
                if not re.search(rf"\b{re.escape(prefix)}:\S", body):
                    unused.append((ttl.stem, prefix))
        self.assertFalse(
            unused,
            f"{len(unused)} unused @prefix declaration(s):\n  "
            + "\n  ".join(f"{f}: @prefix {p}:" for f, p in unused),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
