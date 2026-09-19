"""Docker Compose security posture (correction pass items 4 and 5).

``docker compose config`` needs a container runtime, which is not available in
every environment (including this sandbox), so the files are validated structurally
here — the properties asserted below are the ones that actually matter:

* PostgreSQL and Redis are not published to the host in the production file;
* the API and the panel are the only externally reachable services;
* PostgreSQL and Redis live on an internal network without external connectivity;
* Redis requires a password supplied through the environment, never hard-coded;
* the development override only binds the data ports to localhost;
* exactly one peer (the panel) is trusted to supply X-Forwarded-For, and the ASGI
  server itself never rewrites the peer address from forwarded headers.

The same files are rendered with ``docker compose config`` in CI.
"""

from __future__ import annotations

import pathlib

import pytest

yaml = pytest.importorskip("yaml", reason="PyYAML is a test dependency")

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE = ROOT / "docker-compose.yml"
DEV = ROOT / "docker-compose.dev.yaml"
ENV_EXAMPLE = ROOT / ".env.example"
DOCKERFILE = ROOT / "backend" / "Dockerfile"
MAKEFILE = ROOT / "Makefile"


@pytest.fixture(scope="module")
def base() -> dict:
    return yaml.safe_load(BASE.read_text())


@pytest.fixture(scope="module")
def dev() -> dict:
    return yaml.safe_load(DEV.read_text())


def test_data_services_are_not_published_in_production(base: dict) -> None:
    services = base["services"]
    assert "ports" not in services["postgres"]
    assert "ports" not in services["redis"]


def test_application_services_remain_reachable(base: dict) -> None:
    services = base["services"]
    assert services["api"]["ports"] == ["${API_PORT:-8000}:8000"]
    assert services["web"]["ports"] == ["${WEB_PORT:-8080}:80"]


def test_data_services_use_the_internal_network(base: dict) -> None:
    services = base["services"]
    assert services["postgres"]["networks"] == ["data"]
    assert services["redis"]["networks"] == ["data"]
    assert set(services["api"]["networks"]) == {"edge", "data"}
    assert base["networks"]["data"]["internal"] is True
    assert not (base["networks"]["edge"] or {}).get("internal")


def test_redis_requires_an_environment_supplied_password(base: dict) -> None:
    command = base["services"]["redis"]["command"]
    assert "--requirepass" in command
    password_arg = command[command.index("--requirepass") + 1]
    assert password_arg == "${REDIS_PASSWORD:?set REDIS_PASSWORD in .env}"
    assert not any(":" in arg and "@" in arg for arg in command), "no credentials in the URL"


def test_api_receives_the_required_secrets_from_the_environment(base: dict) -> None:
    env = base["services"]["api"]["environment"]
    assert "${XEREX_SECRET_KEY:?set XEREX_SECRET_KEY in .env}" in env["XEREX_SECRET_KEY"]
    assert "XEREX_CREDENTIALS_ENCRYPTION_KEY:?" in env["XEREX_CREDENTIALS_ENCRYPTION_KEY"]
    assert env["XEREX_BOOTSTRAP_ENABLED"] == "${XEREX_BOOTSTRAP_ENABLED:-false}"
    assert env["XEREX_REDIS_PASSWORD"].startswith("${REDIS_PASSWORD:?")
    assert "XEREX_REDIS_URL" in env
    assert "@" not in env["XEREX_REDIS_URL"], "no credentials inside the Redis URL"
    assert env["XEREX_TRUSTED_PROXIES"]  # proxies are declared explicitly


def test_only_the_panel_container_is_trusted_for_forwarded_headers(base: dict) -> None:
    """A published API port must not let a direct client spoof its address."""
    api_env = base["services"]["api"]["environment"]
    panel_ip = base["services"]["web"]["networks"]["edge"]["ipv4_address"]

    trusted = api_env["XEREX_TRUSTED_PROXIES"]
    assert trusted == f'${{XEREX_TRUSTED_PROXIES:-["{panel_ip}"]}}'
    assert "/32" not in trusted and "/24" not in trusted, "trust one host, not a subnet"
    # The panel address must be the fixed one the edge network reserves, and the
    # single trusted host must not be the network gateway (that is where traffic to
    # the published API port comes from).
    subnet = base["networks"]["edge"]["ipam"]["config"][0]["subnet"]
    assert subnet == "172.28.0.0/24"
    gateway = subnet.rsplit(".", 1)[0] + ".1"
    assert panel_ip != gateway
    assert panel_ip.startswith(subnet.split("/")[0].rsplit(".", 1)[0] + ".")


def test_asgi_server_hands_the_real_peer_to_the_application() -> None:
    """uvicorn's own --proxy-headers would bypass XEREX_TRUSTED_PROXIES."""
    dockerfile = DOCKERFILE.read_text()
    assert "--no-proxy-headers" in dockerfile
    assert "FORWARDED_ALLOW_IPS" not in dockerfile

    makefile = MAKEFILE.read_text()
    run_lines = [line for line in makefile.splitlines() if "uvicorn" in line]
    assert run_lines, "the development server command is missing"
    for line in run_lines:
        assert "--no-proxy-headers" in line, f"proxy headers enabled: {line.strip()}"

    for path in (BASE, DEV):
        text = path.read_text()
        assert "FORWARDED_ALLOW_IPS" not in text, f"{path.name} overrides uvicorn proxy trust"


def test_api_depends_on_healthy_data_services(base: dict) -> None:
    depends_on = base["services"]["api"]["depends_on"]
    assert depends_on["postgres"]["condition"] == "service_healthy"
    assert depends_on["redis"]["condition"] == "service_healthy"


def test_development_override_only_exposes_localhost_ports(dev: dict) -> None:
    services = dev["services"]
    for name, service in services.items():
        for entry in service.get("ports", []):
            assert entry.startswith("127.0.0.1:"), f"{name} publishes {entry}"


def test_development_override_keeps_the_api_convenient(dev: dict) -> None:
    env = dev["services"]["api"]["environment"]
    assert env["XEREX_ENVIRONMENT"] == "development"
    assert env["XEREX_BOOTSTRAP_ENABLED"] == "true"
    assert env["XEREX_REDIS_PASSWORD"]  # injected, not embedded in the URL
    assert env["XEREX_DATABASE_URL"].startswith("postgresql+asyncpg://")


def test_env_example_documents_the_new_settings() -> None:
    text = ENV_EXAMPLE.read_text()
    for key in (
        "XEREX_TRUSTED_PROXIES",
        "XEREX_REDIS_PASSWORD",
        "XEREX_REDIS_USERNAME",
        "XEREX_CREDENTIALS_ENCRYPTION_KEY",
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
    ):
        assert key in text, f"{key} is missing from .env.example"

    # The template must not ship a value that would pass production validation.
    assert "XEREX_SECRET_KEY=change-me-in-production" in text
