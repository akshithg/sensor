"""Serve the SENSOR Lite demo and local analysis API."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from sensor_lite import AnalysisError, analyze_source, build_demo
from sensor_lite.analyzer import score_against_patterns
from sensor_lite.demo_data import prepare_kernel_source

ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
MAX_REQUEST_BYTES = 100_000


class DemoHandler(SimpleHTTPRequestHandler):
    """Serve static UI files and JSON analysis endpoints."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize a handler rooted at the bundled web directory."""
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def _json_response(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        """Return the demo payload or a static asset."""
        if self.path == "/api/demo":
            try:
                self._json_response(build_demo())
            except AnalysisError as error:
                self._json_response({"error": str(error)}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        super().do_GET()

    def do_POST(self) -> None:
        """Analyze a submitted C source snippet."""
        if self.path != "/api/analyze":
            self._json_response({"error": "endpoint not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json_response({"error": "invalid Content-Length"}, HTTPStatus.BAD_REQUEST)
            return
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._json_response(
                {"error": "request body must be between 1 and 100,000 bytes"},
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
            return
        try:
            payload = json.loads(self.rfile.read(length))
            source = payload.get("source")
            patterns = payload.get("patterns", [])
            profile = payload.get("profile")
            if not isinstance(source, str) or not isinstance(patterns, list):
                raise ValueError("source must be text and patterns must be a list")
            analysis_source = prepare_kernel_source(source) if profile == "linux-gnttab" else source
            analysis = analyze_source(analysis_source)
            score = score_against_patterns(analysis, patterns)
        except (json.JSONDecodeError, ValueError, AnalysisError) as error:
            self._json_response({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        self._json_response({"analysis": analysis, "score": score})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Keep request logging concise."""
        print(f"[sensor-lite] {self.address_string()} {format % args}")


def parse_args() -> argparse.Namespace:
    """Parse server command-line arguments."""
    parser = argparse.ArgumentParser(description="Run the SENSOR Lite demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


def main() -> None:
    """Run the local threaded HTTP server."""
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    print(f"SENSOR Lite is running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SENSOR Lite")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
