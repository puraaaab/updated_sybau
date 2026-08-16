import os
import re
import pytest
from backend.main import app


def test_infra_01_nginx_configuration_and_route_coverage():
    """INFRA-01: Verify Nginx reverse proxy configuration covers all FastAPI routes, WebSockets, and health checks."""
    nginx_conf_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "nginx.conf")
    assert os.path.exists(nginx_conf_path), "frontend/nginx.conf must exist"

    with open(nginx_conf_path, "r", encoding="utf-8") as f:
        conf = f.read()

    # 1. Verify client body size is at least 50M
    match = re.search(r"client_max_body_size\s+(\d+)M;", conf)
    assert match, "client_max_body_size must be configured in nginx.conf"
    assert int(match.group(1)) >= 50, f"client_max_body_size should be at least 50M, got {match.group(1)}M"

    # 2. Verify WebSocket location block and required headers
    assert "location /api/v1/ws/" in conf, "Nginx must contain location block for /api/v1/ws/"
    ws_block_match = re.search(r"location /api/v1/ws/\s*\{([^}]+)\}", conf)
    assert ws_block_match, "Valid block for /api/v1/ws/ not found"
    ws_block = ws_block_match.group(1)
    assert "proxy_http_version 1.1;" in ws_block
    assert "Upgrade" in ws_block
    assert 'Connection "Upgrade";' in ws_block
    assert "proxy_buffering off;" in ws_block
    assert "proxy_read_timeout 86400s;" in ws_block

    # 3. Verify REST API proxy
    assert "location /api/" in conf
    assert "proxy_pass http://backend:8000/api/;" in conf

    # 4. Verify Health and OpenAPI docs proxy
    assert "location ~ ^/(healthz|readyz|metrics)" in conf
    assert "location ~ ^/(docs|redoc|openapi\.json)" in conf

    # 5. Enumerate all OpenAPI paths and verify they match Nginx location patterns
    openapi = app.openapi()
    openapi_paths = openapi.get("paths", {}).keys()
    assert len(openapi_paths) >= 50, f"Expected at least 50 OpenAPI endpoints, got {len(openapi_paths)}"

    for path in openapi_paths:
        if path.startswith("/api/"):
            # Matches location /api/ or location /api/v1/ws/
            assert True
        elif path in ("/healthz", "/readyz", "/metrics", "/docs", "/redoc", "/openapi.json"):
            # Matches health/docs location block
            assert True
        else:
            pytest.fail(f"Unproxied route found in OpenAPI schema: {path}")


def test_infra_01_dockerfile_frontend_uses_nginx_conf():
    """INFRA-01: Verify Dockerfile.frontend copies the production nginx.conf."""
    dockerfile_path = os.path.join(os.path.dirname(__file__), "..", "..", "Dockerfile.frontend")
    assert os.path.exists(dockerfile_path)
    with open(dockerfile_path, "r", encoding="utf-8") as f:
        dockerfile = f.read()

    assert "COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf" in dockerfile
    assert "RUN echo 'server {" not in dockerfile, "Inline RUN echo server block must be removed"


def test_infra_02_docker_compose_kafka_bootstrap_port():
    """INFRA-02: Verify docker-compose.yml configures internal kafka:29092 broker address for backend service."""
    compose_path = os.path.join(os.path.dirname(__file__), "..", "..", "docker-compose.yml")
    assert os.path.exists(compose_path)

    with open(compose_path, "r", encoding="utf-8") as f:
        compose_content = f.read()

    # Backend environment must specify kafka:29092
    assert "KAFKA_BOOTSTRAP_SERVERS=kafka:29092" in compose_content
    assert "KAFKA_BOOTSTRAP_SERVERS=kafka:9092" not in compose_content


def test_infra_02_kafka_client_and_main_dynamic_bootstrap_resolution(monkeypatch):
    """INFRA-02: Verify KafkaEventClient and main.py dynamically read and parse comma-separated KAFKA_BOOTSTRAP_SERVERS."""
    test_brokers = "broker1:9092, broker2:9092, broker3:9092"
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", test_brokers)
    monkeypatch.setenv("USE_MEMORY_BUS_ONLY", "true")

    from backend.messaging.kafka_client import KafkaEventClient
    client = KafkaEventClient()
    assert client.bootstrap_servers == ["broker1:9092", "broker2:9092", "broker3:9092"]
