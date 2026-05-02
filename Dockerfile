FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir -e .

# Copy example and test files
COPY examples/ examples/
COPY tests/ tests/

# Default port for SSE Dashboard
EXPOSE 8080

# Environment variables (override at runtime)
ENV LONGCAT_API_KEY=""
ENV LONGCAT_API_BASE="https://api.longcat.chat/openai"

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/metrics')" || exit 1

# Default: run the SSE dashboard
CMD ["python", "-m", "traffic_agent.cli", "simulate", "--steps", "500", "--port", "8080"]
