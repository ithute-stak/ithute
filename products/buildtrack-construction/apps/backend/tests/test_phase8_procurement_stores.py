from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app

ADMIN_PASSWORD = "Nthane!Secure2026X"
BRANCH_PASSWORD = "Proc!Branch2026X"
HQ_PASSWORD = "Proc!HQ2026X"


@pytest.fixture()
def clients():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    admin, branch, hq = TestClient(app), TestClient(app), TestClient(app)
    try:
        yield admin, branch, hq
    finally:
        admin.close(); branch.close(); hq.close(); app.dependency_overrides.clear(); Base.metadata.drop_all(engine)


def bootstrap(admin: TestClient) -> tuple[int, int]:
    assert admin.post("/api/v1/foundation/bootstrap", json={"name":"Nthane Brothers","code":"NTHANE","head_office_name":"Head Office","head_office_code":"HO","head_office_district":"Maseru"}).status_code == 201
    assert admin.post("/api/v1/access/bootstrap-admin", json={"username":"admin","email":"admin@nthane.example","full_name":"System Administrator","password":ADMIN_PASSWORD}).status_code == 201
    response = admin.post("/api/v1/procurement/bootstrap")
    assert response.status_code == 200, response.text
    catalog = admin.get("/api/v1/procurement/catalog")
    assert catalog.status_code == 200, catalog.text
    branch_id = catalog.json()["branches"][0]["id"]
    return branch_id, catalog.json()["branches"][0]["id"]


def create_approvers(admin: TestClient, branch_client: TestClient, hq_client: TestClient, branch_id: int) -> None:
    roles = admin.get("/api/v1/access/assignment-catalog").json()["roles"]
    branch_role = next(row for row in roles if row["code"] == "BRANCH_MANAGER")
    hq_role = next(row for row in roles if row["code"] == "HQ_EXECUTIVE")
    response = admin.post("/api/v1/access/users", json={"username":"procbranch","email":"procbranch@nthane.example","full_name":"Procurement Branch Approver","temporary_password":BRANCH_PASSWORD,"must_change_password":False,"assignments":[{"role_id":branch_role["id"],"branch_id":branch_id,"is_primary":True}]})
    assert response.status_code == 201, response.text
    response = admin.post("/api/v1/access/users", json={"username":"prochq","email":"prochq@nthane.example","full_name":"Procurement HQ Approver","temporary_password":HQ_PASSWORD,"must_change_password":False,"assignments":[{"role_id":hq_role["id"],"is_primary":True}]})
    assert response.status_code == 201, response.text
    assert branch_client.post("/api/v1/access/login", json={"username":"procbranch","password":BRANCH_PASSWORD}).status_code == 200
    assert hq_client.post("/api/v1/access/login", json={"username":"prochq","password":HQ_PASSWORD}).status_code == 200


def approve(branch: TestClient, hq: TestClient, request_id: int) -> None:
    first = branch.post(f"/api/v1/procurement/approvals/{request_id}/decision", json={"decision":"approve","comment":"Branch reviewed"})
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "pending"
    second = hq.post(f"/api/v1/procurement/approvals/{request_id}/decision", json={"decision":"approve","comment":"HQ approved"})
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "approved"


def test_requisition_quote_po_receipt_issue_and_transfer(clients) -> None:
    admin, branch, hq = clients
    branch_id, _ = bootstrap(admin)
    create_approvers(admin, branch, hq, branch_id)

    supplier = admin.post("/api/v1/procurement/suppliers", json={"name":"Maseru Construction Supplies","categories":["materials"],"payment_terms_days":30,"status":"active"})
    assert supplier.status_code == 201, supplier.text
    supplier_id = supplier.json()["id"]

    store_a = admin.post("/api/v1/procurement/locations", json={"branch_id":branch_id,"code":"HO-MAIN","name":"Head Office Main Store","location_type":"branch_store"})
    store_b = admin.post("/api/v1/procurement/locations", json={"branch_id":branch_id,"code":"HO-YARD","name":"Head Office Yard","location_type":"yard"})
    assert store_a.status_code == 201 and store_b.status_code == 201
    store_a_id, store_b_id = store_a.json()["id"], store_b.json()["id"]

    item = admin.post("/api/v1/procurement/items", json={"sku":"CEM-50","description":"50kg Cement","category":"materials","unit":"bag","reorder_level":"3","default_unit_cost":"100","stock_controlled":True})
    assert item.status_code == 201, item.text
    item_id = item.json()["id"]

    req = admin.post("/api/v1/procurement/requisitions", json={"branch_id":branch_id,"title":"Cement for test works","required_by":(date.today()+timedelta(days=7)).isoformat(),"priority":"normal"})
    assert req.status_code == 201, req.text
    req_id = req.json()["id"]
    line = admin.post(f"/api/v1/procurement/requisitions/{req_id}/lines", json={"stock_item_id":item_id,"description":"50kg Cement","quantity":"10","unit":"bag","estimated_unit_cost":"100"})
    assert line.status_code == 201, line.text
    req_line_id = line.json()["id"]
    submitted = admin.post(f"/api/v1/procurement/requisitions/{req_id}/submit")
    assert submitted.status_code == 200, submitted.text
    approve(branch, hq, submitted.json()["id"])
    assert admin.get(f"/api/v1/procurement/requisitions/{req_id}").json()["requisition"]["status"] == "approved"

    quote = admin.post(f"/api/v1/procurement/requisitions/{req_id}/quotations", json={
        "supplier_id":supplier_id,"quote_reference":"Q-001","quote_date":date.today().isoformat(),"valid_until":(date.today()+timedelta(days=30)).isoformat(),"delivery_days":5,"tax_amount":"0",
        "lines":[{"requisition_line_id":req_line_id,"quantity":"10","unit_price":"90"}],
    })
    assert quote.status_code == 201, quote.text
    quote_id = quote.json()["id"]
    selected = admin.post(f"/api/v1/procurement/quotations/{quote_id}/select")
    assert selected.status_code == 200, selected.text
    assert selected.json()["status"] == "selected"

    po = admin.post("/api/v1/procurement/purchase-orders", json={"requisition_id":req_id,"quotation_id":quote_id,"delivery_location_id":store_a_id,"order_date":date.today().isoformat(),"expected_delivery_date":(date.today()+timedelta(days=5)).isoformat()})
    assert po.status_code == 201, po.text
    po_id = po.json()["id"]
    po_submit = admin.post(f"/api/v1/procurement/purchase-orders/{po_id}/submit")
    assert po_submit.status_code == 200, po_submit.text
    approve(branch, hq, po_submit.json()["id"])

    detail = admin.get(f"/api/v1/procurement/purchase-orders/{po_id}")
    assert detail.status_code == 200, detail.text
    po_line_id = detail.json()["lines"][0]["id"]

    first_receipt = admin.post(f"/api/v1/procurement/purchase-orders/{po_id}/receipts", json={"receipt_date":date.today().isoformat(),"delivery_reference":"DN-001","lines":[{"purchase_order_line_id":po_line_id,"quantity_received":"10","quantity_accepted":"8","quantity_rejected":"2"}]})
    assert first_receipt.status_code == 201, first_receipt.text
    assert first_receipt.json()["purchase_order_status"] == "part_received"

    second_receipt = admin.post(f"/api/v1/procurement/purchase-orders/{po_id}/receipts", json={"receipt_date":date.today().isoformat(),"delivery_reference":"DN-002","lines":[{"purchase_order_line_id":po_line_id,"quantity_received":"2","quantity_accepted":"2","quantity_rejected":"0"}]})
    assert second_receipt.status_code == 201, second_receipt.text
    assert second_receipt.json()["purchase_order_status"] == "received"

    stock = admin.get("/api/v1/procurement/stock").json()
    cement = next(row for row in stock if row["location_id"] == store_a_id and row["stock_item_id"] == item_id)
    assert cement["quantity_on_hand"] == "10.000"
    assert cement["average_unit_cost"] == "90.0000"

    issued = admin.post("/api/v1/procurement/stock/issues", json={"location_id":store_a_id,"stock_item_id":item_id,"quantity":"3","reason":"Issue to controlled works"})
    assert issued.status_code == 201, issued.text
    too_much = admin.post("/api/v1/procurement/stock/issues", json={"location_id":store_a_id,"stock_item_id":item_id,"quantity":"8","reason":"Must fail negative stock guard"})
    assert too_much.status_code == 409

    transfer = admin.post("/api/v1/procurement/transfers", json={"from_location_id":store_a_id,"to_location_id":store_b_id,"lines":[{"stock_item_id":item_id,"quantity":"2"}]})
    assert transfer.status_code == 201, transfer.text
    transfer_id = transfer.json()["id"]
    shipped = admin.post(f"/api/v1/procurement/transfers/{transfer_id}/ship")
    assert shipped.status_code == 200, shipped.text
    received = admin.post(f"/api/v1/procurement/transfers/{transfer_id}/receive")
    assert received.status_code == 200, received.text

    stock = admin.get("/api/v1/procurement/stock").json()
    source = next(row for row in stock if row["location_id"] == store_a_id and row["stock_item_id"] == item_id)
    destination = next(row for row in stock if row["location_id"] == store_b_id and row["stock_item_id"] == item_id)
    assert source["quantity_on_hand"] == "5.000"
    assert destination["quantity_on_hand"] == "2.000"
    assert destination["average_unit_cost"] == "90.0000"

    movements = admin.get("/api/v1/procurement/stock/movements").json()
    movement_types = {row["movement_type"] for row in movements}
    assert {"receipt", "issue", "transfer_out", "transfer_in"}.issubset(movement_types)

    exported = admin.get("/api/v1/procurement/exports/stock.csv")
    assert exported.status_code == 200 and "CEM-50" in exported.text
