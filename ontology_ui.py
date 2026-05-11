"""
ontology_ui.py
==============
CLI entry point for the AMT Ontology Browser.

The application code lives in the ``app`` package — this file exists purely
to keep the historical ``python ontology_ui.py`` invocation working. All it
does is parse CLI flags and hand a configured Flask app off to its
development server.

Usage
-----
    python ontology_ui.py [--host HOST] [--port PORT] [--ontology-dir DIR]

The ``--ontology-dir`` flag is optional; when omitted the app reads
``ontology/`` from the repository root. Tests pass an explicit directory
to ``app.create_app`` directly and never go through this file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.routes import create_app


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AMT Ontology Browser - Flask development server.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host address to bind to (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to listen on (default: 5000).",
    )
    parser.add_argument(
        "--ontology-dir",
        type=Path,
        default=None,
        help="Override the default ontology/ directory (absolute or relative).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    app = create_app(ontology_dir=args.ontology_dir)
    print(
        f"AMT Ontology Browser listening on http://{args.host}:{args.port}",
        file=sys.stderr,
    )
    app.run(host=args.host, port=args.port, debug=True)


if __name__ == "__main__":
    main()
