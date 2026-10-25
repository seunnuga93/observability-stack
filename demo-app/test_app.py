import json
import threading
import urllib.error
import urllib.request

import pytest

import app


@pytest.fixture(scope="module")
def base_url():
    server = app.serve(port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def get(url):
    try:
        with urllib.request.urlopen(url) as resp:  # noqa: S310
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


def test_healthz(base_url):
    assert get(f"{base_url}/healthz") == (200, "ok")


def test_routes_record_metrics(base_url):
    for _ in range(5):
        status, _ = get(f"{base_url}/api/orders")
        assert status in (200, 500)
    _, metrics = get(f"{base_url}/metrics")
    assert 'http_requests_total{path="/api/orders"' in metrics
    assert 'http_request_duration_seconds_bucket{le="0.01",path="/api/orders"}' in metrics


def test_unknown_path_is_404(base_url):
    assert get(f"{base_url}/nope")[0] == 404


def test_alert_webhook_counts_alerts(base_url):
    payload = {"alerts": [{"status": "firing", "labels": {"alertname": "TargetDown"}}]}
    req = urllib.request.Request(
        f"{base_url}/alert-webhook",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        assert resp.status == 200
    _, metrics = get(f"{base_url}/metrics")
    assert 'alerts_received_total{status="firing"} 1.0' in metrics
