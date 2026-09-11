"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { nbrosApi } from "@/lib/backend";

function value(formData: FormData, key: string): string {
  return String(formData.get(key) ?? "").trim();
}

function optional(formData: FormData, key: string): string | null {
  const result = value(formData, key);
  return result || null;
}

function numberOrNull(formData: FormData, key: string): number | null {
  const raw = optional(formData, key);
  return raw === null ? null : Number(raw);
}

function refresh(branchId: string, path: string): never {
  revalidatePath("/operations");
  revalidatePath(path);
  redirect(`${path}?branch=${branchId}`);
}

export async function createTechnicianAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/operations/workshop/technicians", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      full_name: value(formData, "full_name"),
      employee_number: optional(formData, "employee_number"),
      specialty: optional(formData, "specialty"),
      hourly_rate: optional(formData, "hourly_rate"),
    }),
  });
  refresh(branchId, "/operations/workshop");
}

export async function createBayAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/operations/workshop/bays", {
    method: "POST",
    body: JSON.stringify({ branch_id: branchId, code: value(formData, "code"), name: value(formData, "name") }),
  });
  refresh(branchId, "/operations/workshop");
}

export async function createWorkshopJobAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/operations/workshop/jobs", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      vehicle_id: value(formData, "vehicle_id"),
      complaint: value(formData, "complaint"),
      priority: value(formData, "priority") || "normal",
      technician_id: optional(formData, "technician_id"),
      bay_id: optional(formData, "bay_id"),
      external_supplier_id: optional(formData, "external_supplier_id"),
      external_quote: optional(formData, "external_quote"),
      expected_release_at: optional(formData, "expected_release_at"),
      service_type: optional(formData, "service_type"),
      service_mileage: numberOrNull(formData, "service_mileage"),
    }),
  });
  refresh(branchId, "/operations/workshop");
}

export async function updateWorkshopCostingAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/operations/workshop/jobs/${value(formData, "job_id")}/costing?branch_id=${branchId}`, {
    method: "PATCH",
    body: JSON.stringify({
      diagnosis: optional(formData, "diagnosis"),
      work_performed: optional(formData, "work_performed"),
      labour_hours: optional(formData, "labour_hours"),
      labour_cost: optional(formData, "labour_cost"),
      external_cost: optional(formData, "external_cost"),
      status: optional(formData, "status"),
    }),
  });
  refresh(branchId, "/operations/workshop");
}

export async function issueWorkshopPartAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/operations/workshop/jobs/${value(formData, "job_id")}/parts?branch_id=${branchId}`, {
    method: "POST",
    body: JSON.stringify({
      inventory_item_id: value(formData, "inventory_item_id"),
      quantity: value(formData, "quantity"),
      unit_cost: optional(formData, "unit_cost"),
    }),
  });
  refresh(branchId, "/operations/workshop");
}

export async function completeWorkshopJobAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/operations/workshop/jobs/${value(formData, "job_id")}/complete?branch_id=${branchId}`, { method: "POST" });
  refresh(branchId, "/operations/workshop");
}

export async function createSupplierAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/operations/suppliers", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      name: value(formData, "name"),
      supplier_type: value(formData, "supplier_type") || "general",
      contact_person: optional(formData, "contact_person"),
      email: optional(formData, "email"),
      phone: optional(formData, "phone"),
    }),
  });
  refresh(branchId, "/operations/stores");
}

export async function createRequisitionAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/operations/procurement/requisitions", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      purpose: value(formData, "purpose"),
      lines: [{
        inventory_item_id: optional(formData, "inventory_item_id"),
        description: value(formData, "description"),
        quantity: value(formData, "quantity"),
        estimated_unit_cost: optional(formData, "estimated_unit_cost"),
      }],
    }),
  });
  refresh(branchId, "/operations/stores");
}

export async function createPurchaseOrderAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/operations/procurement/requisitions/${value(formData, "requisition_id")}/order?branch_id=${branchId}`, {
    method: "POST",
    body: JSON.stringify({ supplier_id: value(formData, "supplier_id"), expected_at: optional(formData, "expected_at") }),
  });
  refresh(branchId, "/operations/stores");
}

export async function receiveGrnAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/operations/procurement/purchase-orders/${value(formData, "purchase_order_id")}/grn?branch_id=${branchId}`, {
    method: "POST",
    body: JSON.stringify({
      reference: value(formData, "reference"),
      notes: optional(formData, "notes"),
      lines: [{ purchase_order_item_id: value(formData, "purchase_order_item_id"), quantity: value(formData, "quantity") }],
    }),
  });
  refresh(branchId, "/operations/stores");
}

export async function decideApprovalAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/operations/approvals/${value(formData, "approval_id")}/decide-routed?branch_id=${branchId}`, {
    method: "POST",
    body: JSON.stringify({ decision: value(formData, "decision"), note: optional(formData, "note") }),
  });
  refresh(branchId, value(formData, "return_path") || "/operations/stores");
}

export async function createApprovalPolicyAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/operations/approval-policies", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      workflow_key: value(formData, "workflow_key"),
      display_name: value(formData, "display_name"),
      min_amount: value(formData, "min_amount") || "0",
      required_role: value(formData, "required_role") || "manager",
      priority: Number(value(formData, "priority") || "100"),
    }),
  });
  refresh(branchId, "/operations/governance");
}

export async function toggleApprovalPolicyAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/operations/approval-policies/${value(formData, "policy_id")}/toggle?branch_id=${branchId}`, { method: "POST" });
  refresh(branchId, "/operations/governance");
}

export async function createDispatchAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/operations/dispatch/requests", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      vehicle_type: value(formData, "vehicle_type"),
      driver_id: optional(formData, "driver_id"),
      destination: value(formData, "destination"),
      purpose: value(formData, "purpose"),
      passenger_count: Number(value(formData, "passenger_count") || "0"),
      load_description: optional(formData, "load_description"),
      start_at: value(formData, "start_at"),
      end_at: value(formData, "end_at"),
    }),
  });
  refresh(branchId, "/operations/dispatch");
}

export async function approveDispatchAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  const vehicleId = optional(formData, "vehicle_id");
  await nbrosApi(`/api/v1/operations/dispatch/requests/${value(formData, "request_id")}/approve?branch_id=${branchId}`, {
    method: "POST",
    body: JSON.stringify({ vehicle_id: vehicleId }),
  });
  refresh(branchId, "/operations/dispatch");
}

export async function startDispatchAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/operations/dispatch/requests/${value(formData, "request_id")}/start?branch_id=${branchId}`, { method: "POST" });
  refresh(branchId, "/operations/dispatch");
}

export async function completeDispatchAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/operations/dispatch/requests/${value(formData, "request_id")}/complete?branch_id=${branchId}`, { method: "POST" });
  refresh(branchId, "/operations/dispatch");
}

export async function createTyreAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/operations/tyres", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      serial_number: value(formData, "serial_number"),
      brand: optional(formData, "brand"),
      size: optional(formData, "size"),
      purchase_date: optional(formData, "purchase_date"),
      purchase_cost: optional(formData, "purchase_cost"),
      current_tread_mm: optional(formData, "current_tread_mm"),
    }),
  });
  refresh(branchId, "/operations/assets");
}

export async function fitTyreAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/operations/tyres/${value(formData, "tyre_id")}/lifecycle/fit?branch_id=${branchId}`, {
    method: "POST",
    body: JSON.stringify({ vehicle_id: value(formData, "vehicle_id"), wheel_position: value(formData, "wheel_position"), odometer_km: Number(value(formData, "odometer_km")), tread_mm: optional(formData, "tread_mm"), notes: optional(formData, "notes") }),
  });
  refresh(branchId, "/operations/assets");
}

export async function rotateTyreAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/operations/tyres/${value(formData, "tyre_id")}/lifecycle/rotate?branch_id=${branchId}`, {
    method: "POST",
    body: JSON.stringify({ wheel_position: value(formData, "wheel_position"), odometer_km: Number(value(formData, "odometer_km")), tread_mm: optional(formData, "tread_mm"), notes: optional(formData, "notes") }),
  });
  refresh(branchId, "/operations/assets");
}

export async function inspectTyreAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/operations/tyres/${value(formData, "tyre_id")}/lifecycle/inspect?branch_id=${branchId}`, {
    method: "POST",
    body: JSON.stringify({ odometer_km: numberOrNull(formData, "odometer_km"), tread_mm: value(formData, "tread_mm"), notes: optional(formData, "notes") }),
  });
  refresh(branchId, "/operations/assets");
}

export async function removeTyreAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  const odometer = optional(formData, "odometer_km");
  await nbrosApi(`/api/v1/operations/tyres/${value(formData, "tyre_id")}/lifecycle/remove?branch_id=${branchId}${odometer ? `&odometer_km=${odometer}` : ""}`, { method: "POST" });
  refresh(branchId, "/operations/assets");
}

export async function createClaimAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/operations/insurance/claims", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      vehicle_id: value(formData, "vehicle_id"),
      insurer: optional(formData, "insurer"),
      claim_number: optional(formData, "claim_number"),
      police_reference: optional(formData, "police_reference"),
      claim_amount: optional(formData, "claim_amount"),
      excess_amount: optional(formData, "excess_amount"),
      notes: optional(formData, "notes"),
    }),
  });
  refresh(branchId, "/operations/assets");
}

export async function createTelematicsAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/operations/telematics/events", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      vehicle_id: value(formData, "vehicle_id"),
      provider: value(formData, "provider") || "manual",
      event_type: value(formData, "event_type"),
      occurred_at: value(formData, "occurred_at"),
      odometer_km: numberOrNull(formData, "odometer_km"),
      speed_kph: optional(formData, "speed_kph"),
      latitude: optional(formData, "latitude"),
      longitude: optional(formData, "longitude"),
    }),
  });
  refresh(branchId, "/operations/assets");
}

export async function createDriverCredentialAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/operations/drivers/credentials", {
    method: "POST",
    body: JSON.stringify({ branch_id: branchId, driver_id: value(formData, "driver_id"), credential_type: value(formData, "credential_type"), reference: optional(formData, "reference"), issue_date: optional(formData, "issue_date"), expiry_date: optional(formData, "expiry_date"), notes: optional(formData, "notes") }),
  });
  refresh(branchId, "/operations/people");
}

export async function createDriverTrainingAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/operations/drivers/training", {
    method: "POST",
    body: JSON.stringify({ branch_id: branchId, driver_id: value(formData, "driver_id"), course_name: value(formData, "course_name"), provider: optional(formData, "provider"), completed_date: value(formData, "completed_date"), expiry_date: optional(formData, "expiry_date"), certificate_reference: optional(formData, "certificate_reference"), notes: optional(formData, "notes") }),
  });
  refresh(branchId, "/operations/people");
}

export async function updateFuelSettingsAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/operations/fuel/settings?branch_id=${branchId}`, {
    method: "PUT",
    body: JSON.stringify({ anomaly_l_per_100km: value(formData, "anomaly_l_per_100km"), price_deviation_percent: value(formData, "price_deviation_percent"), minimum_distance_km: Number(value(formData, "minimum_distance_km")) }),
  });
  refresh(branchId, "/operations/finance");
}

export async function updateBudgetAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/operations/finance/budgets", {
    method: "PUT",
    body: JSON.stringify({
      branch_id: branchId,
      year: Number(value(formData, "year")),
      month: Number(value(formData, "month")),
      budget_amount: value(formData, "budget_amount"),
      notes: optional(formData, "notes"),
    }),
  });
  refresh(branchId, "/operations/finance");
}
