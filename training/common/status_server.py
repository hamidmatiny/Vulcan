#!/usr/bin/env python3
"""Optional training status HTTP (/health + /metrics) for ports 9011–9013."""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--result", type=Path, default=None)
    args = parser.parse_args()
    result_path = args.result

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                body = json.dumps({"status": "ok", "backend": args.backend}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/metrics":
                lines = [
                    "# HELP vulcan_training_status Training status gauge",
                    "# TYPE vulcan_training_status gauge",
                    f'vulcan_training_status{{backend="{args.backend}"}} 1',
                ]
                if result_path and result_path.is_file():
                    data = json.loads(result_path.read_text(encoding="utf-8"))
                    m = data.get("metrics") or {}
                    lines.append(
                        f'vulcan_training_steps_per_sec{{backend="{args.backend}"}} '
                        f'{float(m.get("steps_per_sec") or 0)}'
                    )
                body = ("\n".join(lines) + "\n").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, fmt: str, *a: object) -> None:
            return

    port = int(os.environ.get("PORT", args.port))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
