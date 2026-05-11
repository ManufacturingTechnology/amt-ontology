"""
app.graphs
==========
Ontology graph loading.

The browser reads each ontology file directly with ``rdflib`` and does **not**
follow ``owl:imports`` — every tab in the UI renders only the contents of its
own file. That keeps startup fast and side-effect-free, and lets each test
pick which graphs it cares about without paying for the others.

This module provides two things:

* :func:`load_graph` – a one-shot parser for a single ``.ttl`` file. Returns
  an empty :class:`rdflib.Graph` (rather than raising) when the file is
  missing, so a partially-built repository still boots.
* :class:`OntologyGraphs` – a lazy container that caches each graph on first
  access. The Flask app uses this so the browser only parses what the user
  is viewing on a given session, and so tests can instantiate the container
  with a custom ``ontology_dir`` (useful in CI where fixtures may live
  elsewhere).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import rdflib

from .paths import ONTOLOGY_DIR

# ---------------------------------------------------------------------------
# Canonical list of ontology stems (used by tests and validation tooling).
# ---------------------------------------------------------------------------

ONTOLOGY_NAMES: tuple[str, ...] = (
    "pc",
    "ind",
    "im",
    "amtmeta",
    "exhibitor_view",
    "visitor_view",
    "ind_view",
)


def load_graph(path: Path | str) -> rdflib.Graph:
    """Parse a Turtle ontology file into a fresh :class:`rdflib.Graph`.

    Missing files return an empty graph rather than raising — callers that
    need strict behaviour should check ``path.exists()`` themselves.
    """
    g = rdflib.Graph()
    path = Path(path)
    if path.exists():
        g.parse(path.as_posix(), format="turtle")
    return g


def load_union(paths: Iterable[Path | str]) -> rdflib.Graph:
    """Parse multiple Turtle files into one combined graph.

    Convenience wrapper used by :mod:`app.validation` so SHACL shapes can see
    the view *and* its source ontology as a single data graph.
    """
    g = rdflib.Graph()
    for p in paths:
        p = Path(p)
        if p.exists():
            g.parse(p.as_posix(), format="turtle")
    return g


class OntologyGraphs:
    """Lazy-loaded container for the seven AMT ontology files.

    Each graph is parsed on first access via :meth:`get` (or one of the
    named properties) and cached for the lifetime of the container. The
    Flask app instantiates one of these at startup; tests typically create
    their own so they can pick a different ``ontology_dir``.
    """

    def __init__(self, ontology_dir: Path | str | None = None):
        self._dir = Path(ontology_dir) if ontology_dir else ONTOLOGY_DIR
        self._cache: dict[str, rdflib.Graph] = {}

    @property
    def ontology_dir(self) -> Path:
        return self._dir

    # ─── core lookup ────────────────────────────────────────────────────────

    def get(self, name: str) -> rdflib.Graph:
        """Return the graph for ``ontology/<name>.ttl``, parsing if needed."""
        if name not in self._cache:
            self._cache[name] = load_graph(self._dir / f"{name}.ttl")
        return self._cache[name]

    # ─── named convenience properties (alphabetical) ────────────────────────

    @property
    def amtmeta(self) -> rdflib.Graph:
        return self.get("amtmeta")

    @property
    def exhibitor(self) -> rdflib.Graph:
        return self.get("exhibitor_view")

    @property
    def im(self) -> rdflib.Graph:
        return self.get("im")

    @property
    def ind(self) -> rdflib.Graph:
        return self.get("ind")

    @property
    def ind_view(self) -> rdflib.Graph:
        return self.get("ind_view")

    @property
    def pc(self) -> rdflib.Graph:
        return self.get("pc")

    @property
    def visitor(self) -> rdflib.Graph:
        return self.get("visitor_view")
