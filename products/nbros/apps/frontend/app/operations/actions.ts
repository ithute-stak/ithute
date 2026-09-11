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

export async function decideApprovalAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/operations/approvals/${value(formData, "approval_id")}/decision?branch_id=${branchId}`, {
    method: "POST",
    body: JSON.stringify({ decision: value(formData, "decision"), note: optional(formData, "note") }),
  });
  refresh(branchId, value(formData, "return_path") || "/operations/stores");
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
  refresh(branchId, "/operations");
}
