# Deployment Guide

This guide covers deploying the LLM Traffic Timing Assistant in various environments.

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -e ".[llm,dev]"

# Run simulation
python -m traffic_agent.cli run --steps 100

# Start API server
python -m traffic_agent.cli serve --port 8080
```

### Docker

```bash
# Build image
docker build -t traffic-agent .

# Run container
docker run -p 8080:8080 -e LONGCAT_API_KEY=your-key traffic-agent

# Using docker-compose
docker-compose up -d
```

### Kubernetes

```bash
# Apply manifests
kubectl apply -k k8s/

# Check status
kubectl get pods -n traffic-agent

# View logs
kubectl logs -f deployment/traffic-agent -n traffic-agent
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LONGCAT_API_KEY` | LLM API key | (required for LLM) |
| `LONGCAT_API_BASE` | LLM API base URL | `https://api.longcat.chat/openai` |

### Configuration File

Create `configs/default.json`:

```json
{
  "simulation": {
    "intersection_type": "crossroad",
    "scenario": "normal",
    "steps": 500,
    "seed": 42
  },
  "signal": {
    "ns_green": 30.0,
    "ew_green": 30.0,
    "min_green": 15.0,
    "max_green": 90.0
  }
}
```

## API Endpoints

### Health Checks

- `GET /healthz` — Liveness probe
- `GET /readyz` — Readiness probe

### Simulation Control

- `POST /api/simulation/start` — Start simulation
- `POST /api/simulation/stop` — Stop simulation
- `GET /api/simulation/status` — Get status
- `GET /api/simulation/state` — Get current state

### Events

- `GET /api/events/stream` — SSE event stream
- `GET /api/events/history` — Event history
- `GET /api/events/metrics` — Aggregated metrics

### Dashboard

- `GET /` — React dashboard
- `GET /docs` — API documentation (OpenAPI)

## Monitoring

### Prometheus Metrics

Metrics are available at `/metrics` (when enabled):

- `simulation_starts_total` — Counter of simulation starts
- `simulation_ends_total` — Counter of simulation ends
- `simulation_duration_seconds` — Histogram of simulation durations
- `timing_adjustments_total` — Counter by layer (rule/cache/llm)

### Logging

Structured logging is available:

```bash
# JSON-like format
python -m traffic_agent.cli run --steps 100 2>&1 | jq .

# Simple format
LOG_FORMAT=simple python -m traffic_agent.cli run --steps 100
```

## Production Considerations

### Security

1. **API Authentication**: Enable API key authentication
   ```python
   from traffic_agent.api.auth import create_default_admin_key
   api_key = create_default_admin_key()
   ```

2. **Rate Limiting**: Configure rate limits per API key

3. **CORS**: Restrict allowed origins in production

### Performance

1. **Caching**: Enable decision cache to reduce LLM calls
2. **Connection Pooling**: Use uvicorn with multiple workers
3. **Resource Limits**: Set appropriate CPU/memory limits in k8s

### High Availability

1. **Replicas**: Run multiple API server replicas
2. **Load Balancing**: Use k8s Service or external LB
3. **Health Checks**: Configure readiness/liveness probes

## Troubleshooting

### Common Issues

1. **Port already in use**
   ```bash
   # Find process using port
   lsof -i :8080
   # Kill process
   kill -9 <PID>
   ```

2. **LLM API errors**
   ```bash
   # Check API key
   echo $LONGCAT_API_KEY
   # Test connection
   curl -H "Authorization: Bearer $LONGCAT_API_KEY" $LONGCAT_API_BASE/models
   ```

3. **Memory issues**
   ```bash
   # Check memory usage
   docker stats
   # Increase limits
   docker run --memory=1g traffic-agent
   ```

### Logs

```bash
# Docker logs
docker logs <container_id>

# Kubernetes logs
kubectl logs -f deployment/traffic-agent -n traffic-agent

# Application logs
python -m traffic_agent.cli run --steps 100 2>&1 | tee app.log
```

## Support

- **Issues**: GitHub Issues
- **Documentation**: docs/ directory
- **Examples**: examples/ directory
