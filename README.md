# observability-stack

![ci](https://github.com/seunnuga93/observability-stack/actions/workflows/ci.yml/badge.svg)

A complete metrics, logs and alerting stack you can bring up with one command: Prometheus,
Alertmanager, Grafana, Loki, Promtail and node-exporter, plus a demo service and load
generator so every dashboard and alert has real data behind it.

## Quick start

```bash
cp .env.example .env    # optional: set a Grafana admin password
docker compose up -d --build
```

| Service | URL |
| --- | --- |
| Grafana | http://localhost:3000 (admin / admin unless set in `.env`) |
| Prometheus | http://localhost:9090 |
| Alertmanager | http://localhost:9093 |
| Demo app | http://localhost:8000/metrics |

Open Grafana, go to **Dashboards → Observability Stack → Service Overview**.

## How it fits together

```
 loadgen ──HTTP──► demo-app ──/metrics──┐
                      │                 ├──► Prometheus ──rules──► Alertmanager ──webhook──► demo-app
 node-exporter ───────┼─────────────────┘        │                                         (logs alert)
                      │ stdout (JSON)            │
 docker.sock ──► Promtail ──────────► Loki       │
                                        │        │
                                        └──► Grafana ◄──┘   (datasources + dashboard provisioned from git)
```

## What's in it

**Prometheus** (`prometheus/`)
- Recording rules for request rate, error ratio and p95 latency, so dashboards and alerts share one definition
- Alerts: target down, error rate > 5%, p95 > 500ms, host CPU/memory, and disk filling within 24h (`predict_linear`)
- **Unit tests for alerts** in `prometheus/tests/alerts_test.yml`, run with `promtool test rules`

**Alertmanager** (`alertmanager/`)
- Routing by severity, grouping, and an inhibit rule so a `TargetDown` suppresses that job's warning alerts
- Receivers point at a webhook on the demo app, which logs each alert so you can see them in Loki. Swap in Slack or PagerDuty for real use.

**Loki + Promtail** (`loki/`, `promtail/`)
- Promtail discovers containers through the Docker socket and labels logs by compose service
- Demo app logs are JSON, and `level` is promoted to a label for cheap filtering
- 7-day retention via the compactor

**Grafana** (`grafana/`)
- Datasources and the dashboard are provisioned as code. Nothing is configured by clicking.

## Try it

Trigger the `TargetDown` alert:

```bash
docker compose stop demo-app
# ~2 minutes later: Prometheus → Alerts shows it firing, then Alertmanager receives it
docker compose start demo-app
```

Query logs in Grafana Explore → Loki:

```logql
{service="demo-app", level="error"} | json | path="/api/checkout"
```

## CI

`.github/workflows/ci.yml`:
1. **validate**: `promtool check config`, `promtool test rules`, `amtool check-config`, dashboard JSON, compose file, and the demo app's tests
2. **integration**: starts the whole stack on the runner, then checks that every Prometheus target is up, Grafana has loaded the dashboard and datasources, and logs are arriving in Loki
