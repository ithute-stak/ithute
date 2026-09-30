from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.application_hosting import ALLOWED_RUNTIMES, HostingProjectCreate
from app.api.v1.hosting_source_credentials import GitCredentialCreate, PrivateGitSourceCreate, _validate_secret
from app.api.v1.shared_hosting import (
    DatabaseAgentStatus,
    GitSourceCreate,
    HostingDatabaseCreate,
    ZipSourceRegister,
    _queue_database_operation,
    _safe_db_name,
    _safe_git_source,
    runtime_catalog,
)


EXPECTED_RUNTIMES = {"static", "node", "python", "php", "dotnet", "java", "go", "ruby", "rust", "dockerfile"}


def test_runtime_catalog_matches_project_validation():
    catalog = runtime_catalog()
    advertised = {item["id"] for item in catalog["items"]}
    assert advertised == EXPECTED_RUNTIMES
    assert ALLOWED_RUNTIMES == EXPECTED_RUNTIMES
    assert set(catalog["database_engines"]) == {"postgresql", "mysql"}
    assert set(catalog["source_types"]) == {"git", "zip"}


@pytest.mark.parametrize("runtime", sorted(EXPECTED_RUNTIMES))
def test_project_create_accepts_every_advertised_runtime(runtime: str):
    model = HostingProjectCreate(name="Customer app", runtime=runtime, accept_hosting_rules=True)
    assert model.runtime == runtime


def test_project_create_rejects_unknown_runtime():
    with pytest.raises(ValidationError):
        HostingProjectCreate(name="Customer app", runtime="unknown-runtime", accept_hosting_rules=True)


@pytest.mark.parametrize("engine", ["postgresql", "mysql"])
def test_database_contract_accepts_supported_engines(engine: str):
    model = HostingDatabaseCreate(engine=engine, name="customer_app")
    assert model.engine == engine


def test_database_contract_rejects_unknown_engine():
    with pytest.raises(ValidationError):
        HostingDatabaseCreate(engine="sqlite", name="customer_app")


def test_database_name_is_normalized_safely():
    assert _safe_db_name("Customer App 2026") == "customer_app_2026"


def test_database_name_must_begin_with_letter():
    with pytest.raises(HTTPException) as exc:
        _safe_db_name("2026 customer")
    assert exc.value.status_code == 422


@pytest.mark.parametrize(
    ("operation", "status"),
    [
        ("provision", "queued"),
        ("rotate", "queued"),
        ("suspend", "queued"),
        ("resume", "queued"),
        ("delete", "deleting"),
    ],
)
def test_database_operation_queue_contract(operation: str, status: str):
    row = SimpleNamespace(operation="none", status="ready", claimed_at="old", completed_at="old", failure_message="old")
    _queue_database_operation(row, operation)
    assert row.operation == operation
    assert row.status == status
    assert row.claimed_at is None
    assert row.completed_at is None
    assert row.failure_message is None


def test_database_operation_queue_rejects_unknown_internal_operation():
    row = SimpleNamespace(operation="none", status="ready", claimed_at=None, completed_at=None, failure_message=None)
    with pytest.raises(RuntimeError):
        _queue_database_operation(row, "destroy-everything")


def test_database_agent_status_validates_port_range():
    assert DatabaseAgentStatus(success=True, host="ithute-db-gateway", port=5432).port == 5432
    with pytest.raises(ValidationError):
        DatabaseAgentStatus(success=True, port=70000)


def test_zip_contract_rejects_oversized_upload():
    with pytest.raises(ValidationError):
        ZipSourceRegister(original_filename="source.zip", size_bytes=2_147_483_649)


def test_git_contract_has_bounded_branch_and_repository_fields():
    model = GitSourceCreate(repository_url="https://github.com/example/project.git", branch="main")
    assert model.repository_url.endswith("project.git")
    assert model.branch == "main"


@pytest.mark.parametrize(
    ("repository_url", "branch"),
    [
        ("https://github.com/example/project.git", "main"),
        ("ssh://git@github.com/example/project.git", "release/2026"),
        ("git@github.com:example/project.git", "feature/shared-hosting"),
    ],
)
def test_safe_git_source_accepts_supported_transports(repository_url: str, branch: str):
    assert _safe_git_source(repository_url, branch) == (repository_url, branch)


def test_safe_git_source_rejects_embedded_https_credentials():
    with pytest.raises(HTTPException) as exc:
        _safe_git_source("https://user:secret@example.com/project.git", "main")
    assert exc.value.status_code == 422
    assert "credentials" in str(exc.value.detail).lower()


@pytest.mark.parametrize("branch", ["-main", "bad branch", "release..next", "feature//bad", "main."])
def test_safe_git_source_rejects_dangerous_branch_names(branch: str):
    with pytest.raises(HTTPException):
        _safe_git_source("https://github.com/example/project.git", branch)


def test_https_git_token_must_be_single_line():
    assert _validate_secret("https_token", "ghp_12345678901234567890") == "ghp_12345678901234567890"
    with pytest.raises(HTTPException):
        _validate_secret("https_token", "token-line-one\ntoken-line-two")


def test_ssh_git_credential_requires_private_key_envelope():
    key = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc123abc123\n-----END OPENSSH PRIVATE KEY-----"
    assert _validate_secret("ssh_key", key) == key
    with pytest.raises(HTTPException):
        _validate_secret("ssh_key", "not-a-private-key")


def test_private_git_contract_requires_project_credential_id():
    model = PrivateGitSourceCreate(
        repository_url="git@github.com:example/private-project.git",
        branch="main",
        credential_id="11111111-1111-1111-1111-111111111111",
    )
    assert str(model.credential_id) == "11111111-1111-1111-1111-111111111111"


def test_git_credential_contract_rejects_unknown_provider():
    with pytest.raises(ValidationError):
        GitCredentialCreate(name="Private repo", provider="unknown", auth_type="https_token", secret="123456789012")
