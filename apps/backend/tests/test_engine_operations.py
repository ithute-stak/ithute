import pytest
from fastapi import HTTPException

from app.api.v1 import engine_operations


def test_enterprise_xml_endpoint_returns_routed_result(monkeypatch):
    monkeypatch.setattr(
        engine_operations,
        "execute_enterprise_xml",
        lambda payload: type(
            "Execution",
            (),
            {
                "operation": "enterprise.xml",
                "engine": "java",
                "value": {"root": "invoice", "element_count": 1},
            },
        )(),
    )
    response = engine_operations.platform_engine_xml_inspect(
        engine_operations.EnterpriseXmlInspectRequest(xml="<invoice/>"),
        current=object(),
    )
    assert response["operation"] == "enterprise.xml"
    assert response["engine"] == "java"
    assert response["result"]["root"] == "invoice"


def test_enterprise_xml_endpoint_maps_invalid_xml_to_422(monkeypatch):
    def fail(_payload):
        raise ValueError("enterprise XML is invalid")

    monkeypatch.setattr(engine_operations, "execute_enterprise_xml", fail)
    with pytest.raises(HTTPException) as exc:
        engine_operations.platform_engine_xml_inspect(
            engine_operations.EnterpriseXmlInspectRequest(xml="<broken>"),
            current=object(),
        )
    assert exc.value.status_code == 422
    assert "invalid" in str(exc.value.detail)
