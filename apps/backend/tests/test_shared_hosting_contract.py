import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.application_hosting import ALLOWED_RUNTIMES, HostingProjectCreate
from app.api.v1.shared_hosting import GitSourceCreate, HostingDatabaseCreate, ZipSourceRegister, _safe_db_name, runtime_catalog


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


def test_zip_contract_rejects_oversized_upload():
    with pytest.raises(ValidationError):
        ZipSourceRegister(original_filename="source.zip", size_bytes=2_147_483_649)


def test_git_contract_has_bounded_branch_and_repository_fields():
    model = GitSourceCreate(repository_url="https://github.com/example/project.git", branch="main")
    assert model.repository_url.endswith("project.git")
    assert model.branch == "main"
