"""Demo service that emits metrics and JSON logs for the observability stack to collect."""

import json
import logging
import random
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS = Counter("http_requests_total", "HTTP requests", ["path", "status"])
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)
ALERTS_RECEIVED = Counter("alerts_received_total", "Alerts received from Alertmanager", ["status"])

# path -> (min latency s, max latency s, error probability)
ROUTES = {
    "/api/orders": (0.01, 0.15, 0.01),
    "/api/checkout": (0.05, 0.40, 0.04),
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {"ts": self.formatTime(record), "level": record.levelname.lower(), "msg": record.getMessage()}
        entry.update(getattr(record, "fields", {}))
        return json.dumps(entry)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
log = logging.getLogger("demo-app")
log.addHandler(handler)
log.setLevel(logging.INFO)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/metrics":
            self._send(200, generate_latest(), CONTENT_TYPE_LATEST)
        elif self.path == "/healthz":
            self._send(200, b"ok")
        elif self.path in ROUTES:
            self._simulate(self.path)
        else:
            self._send(404, b"not found")

    def do_POST(self) -> None:
        if self.path != "/alert-webhook":
            self._send(404, b"not found")
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        for alert in body.get("alerts", []):
            ALERTS_RECEIVED.labels(alert.get("status", "unknown")).inc()
            log.warning(
                "alert received",
                extra={"fields": {"alert": alert.get("labels", {}).get("alertname"), "status": alert.get("status")}},
            )
        self._send(200, b"ok")

    def _simulate(self, path: str) -> None:
        low, high, error_rate = ROUTES[path]
        start = time.perf_counter()
        time.sleep(random.uniform(low, high))  # noqa: S311 - not security sensitive
        status = 500 if random.random() < error_rate else 200  # noqa: S311
        self._send(status, b"error" if status == 500 else b"ok")
        duration = time.perf_counter() - start
        LATENCY.labels(path).observe(duration)
        REQUESTS.labels(path, str(status)).inc()
        level = logging.ERROR if status == 500 else logging.INFO
        log.log(
            level, "request", extra={"fields": {"path": path, "status": status, "duration_ms": round(duration * 1000)}}
        )

    def _send(self, status: int, body: bytes, content_type: str = "text/plain") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass  # access logs are replaced by the structured log line above


def serve(port: int = 8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("0.0.0.0", port), Handler)  # noqa: S104 - runs in a container


if __name__ == "__main__":
    log.info("starting", extra={"fields": {"port": 8000}})
    serve().serve_forever()
