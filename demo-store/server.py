"""Static server for the Nimbus Supply demo store.

Usage:
    python server.py --dir . --port 8090

The server is deliberately tiny and dependency-free: verification runs start it
from an isolated checkout so the patch under test is the one actually served.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class DemoStoreHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if self.path.split("?")[0] == "/health":
            body = json.dumps({"status": "ok", "app": "nimbus-supply"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Demo-Target", "nimbus-supply")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Nimbus Supply demo store")
    parser.add_argument("--dir", default=os.path.dirname(os.path.abspath(__file__)))
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    handler = partial(DemoStoreHandler, directory=os.path.abspath(args.dir))
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"demo-store serving {os.path.abspath(args.dir)} at http://{args.host}:{args.port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()