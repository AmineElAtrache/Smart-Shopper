"""Simple HTTP health and metrics server for Kubernetes probes."""

from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Callable

from shared.runtime.metrics import MetricsRegistry, get_default_metrics


class HealthServer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        metrics: MetricsRegistry | None = None,
        ready_check: Callable[[], bool] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._metrics = metrics or get_default_metrics()
        self._ready_check = ready_check or (lambda: True)
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    async def start(self) -> None:
        if self._server is not None:
            return

        handler = self._build_handler()
        self._server = ThreadingHTTPServer((self._host, self._port), handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        await asyncio.sleep(0)

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None
        await asyncio.sleep(0)

    def _build_handler(self) -> type[BaseHTTPRequestHandler]:
        metrics = self._metrics
        ready_check = self._ready_check

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib API
                if self.path == "/healthz":
                    self._send_text("ok\n", status=200)
                    return
                if self.path == "/readyz":
                    is_ready = ready_check()
                    body = "ready\n" if is_ready else "not ready\n"
                    self._send_text(body, status=200 if is_ready else 503)
                    return
                if self.path == "/metrics":
                    self._send_text(metrics.render_prometheus(), status=200)
                    return
                self._send_text("not found\n", status=404)

            def log_message(self, format: str, *args: object) -> None:
                return

            def _send_text(self, body: str, *, status: int) -> None:
                payload = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        return Handler
