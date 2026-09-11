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

function operationRedirect(branchId: string) {
  revalidatePath("/fleet");
  revalidatePath("/fleet/operations");
  redirect(`/fleet/operations?branch=${branchId}`);
}

export async function createDriverAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/fleet/drivers", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      employee_number: optional(formData, "employee_number"),
      full_name: value(formData, "full_name"),
      license_number: value(formData, "license_number"),
      license_category: value(formData, "license_category"),
      license_expiry: value(formData, "license_expiry"),
    }),
  });
  revalidatePath("/fleet/drivers");
  redirect(`/fleet/drivers?branch=${branchId}`);
}

export async function addMaintenanceAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/fleet/maintenance", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      vehicle_id: value(formData, "vehicle_id"),
      description: value(formData, "description"),
      expected_release_at: optional(formData, "expected_release_at"),
    }),
  });
  operationRedirect(branchId);
}

export async function closeMaintenanceAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/fleet/maintenance/${value(formData, "id")}/close`, { method: "POST" });
  operationRedirect(branchId);
}

export async function addAssignmentAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/fleet/assignments", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      vehicle_id: value(formData, "vehicle_id"),
      driver_id: value(formData, "driver_id"),
      purpose: optional(formData, "purpose"),
      start_at: value(formData, "start_at"),
      end_at: optional(formData, "end_at"),
    }),
  });
  operationRedirect(branchId);
}

export async function completeAssignmentAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/fleet/assignments/${value(formData, "id")}/complete`, { method: "POST" });
  operationRedirect(branchId);
}

export async function addTripAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/fleet/trips", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      vehicle_id: value(formData, "vehicle_id"),
      driver_id: value(formData, "driver_id"),
      destination: value(formData, "destination"),
      purpose: optional(formData, "purpose"),
      start_at: value(formData, "start_at"),
      expected_return_at: optional(formData, "expected_return_at"),
    }),
  });
  operationRedirect(branchId);
}

export async function returnTripAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/fleet/trips/${value(formData, "id")}/return`, { method: "POST" });
  operationRedirect(branchId);
}

export async function addReservationAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/fleet/reservations", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      vehicle_id: value(formData, "vehicle_id"),
      driver_id: optional(formData, "driver_id"),
      purpose: optional(formData, "purpose"),
      start_at: value(formData, "start_at"),
      end_at: value(formData, "end_at"),
    }),
  });
  operationRedirect(branchId);
}

export async function cancelReservationAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/fleet/reservations/${value(formData, "id")}/cancel`, { method: "POST" });
  operationRedirect(branchId);
}

export async function addFuelAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/fleet/fuel", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      vehicle_id: value(formData, "vehicle_id"),
      mileage: Number(value(formData, "mileage")),
      litres: value(formData, "litres"),
      cost: optional(formData, "cost"),
      station: optional(formData, "station"),
    }),
  });
  operationRedirect(branchId);
}

export async function addAccidentAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/fleet/accidents", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      vehicle_id: value(formData, "vehicle_id"),
      driver_id: optional(formData, "driver_id"),
      occurred_at: value(formData, "occurred_at"),
      location: optional(formData, "location"),
      description: value(formData, "description"),
      reference_number: optional(formData, "reference_number"),
    }),
  });
  operationRedirect(branchId);
}

export async function updateFleetSettingsAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi(`/api/v1/fleet/branches/${branchId}/settings`, {
    method: "PUT",
    body: JSON.stringify({
      document_warning_days: Number(value(formData, "document_warning_days")),
      document_critical_days: Number(value(formData, "document_critical_days")),
      service_warning_days: Number(value(formData, "service_warning_days")),
      service_mileage_warning: Number(value(formData, "service_mileage_warning")),
    }),
  });
  revalidatePath("/fleet/settings");
  redirect(`/fleet/settings?branch=${branchId}`);
}

export async function addLicenceRuleAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/fleet/license-rules", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      vehicle_type: value(formData, "vehicle_type"),
      license_category: value(formData, "license_category"),
    }),
  });
  revalidatePath("/fleet/settings");
  redirect(`/fleet/settings?branch=${branchId}`);
}

export async function addServiceKitRuleAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/fleet/service-kit-rules", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      make: value(formData, "make"),
      model: value(formData, "model"),
      service_type: value(formData, "service_type"),
      kit_name: value(formData, "kit_name"),
    }),
  });
  revalidatePath("/fleet/settings");
  redirect(`/fleet/settings?branch=${branchId}`);
}

export async function addDocumentRequirementAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/fleet/document-requirements", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      document_type: value(formData, "document_type"),
      vehicle_type: optional(formData, "vehicle_type"),
      is_required: true,
      warning_days: optional(formData, "warning_days") ? Number(value(formData, "warning_days")) : null,
      critical_days: optional(formData, "critical_days") ? Number(value(formData, "critical_days")) : null,
    }),
  });
  revalidatePath("/fleet/settings");
  redirect(`/fleet/settings?branch=${branchId}`);
}
