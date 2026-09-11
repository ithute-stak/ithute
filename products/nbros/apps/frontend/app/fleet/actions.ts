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

export async function createBranchAction(formData: FormData) {
  const branch = await nbrosApi<{ id: string }>("/api/v1/fleet/branches", {
    method: "POST",
    body: JSON.stringify({
      code: value(formData, "code"),
      name: value(formData, "name"),
      location: optional(formData, "location"),
    }),
  });
  revalidatePath("/fleet");
  redirect(`/fleet?branch=${branch.id}`);
}

export async function createVehicleAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  const vehicle = await nbrosApi<{ id: string }>("/api/v1/fleet/vehicles", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      registration_plate: value(formData, "registration_plate"),
      make: value(formData, "make"),
      model: value(formData, "model"),
      vehicle_type: value(formData, "vehicle_type"),
      year: optional(formData, "year") ? Number(value(formData, "year")) : null,
      vin: optional(formData, "vin"),
      engine_number: optional(formData, "engine_number"),
      fuel_type: optional(formData, "fuel_type"),
      current_mileage: Number(value(formData, "current_mileage") || 0),
      purchase_date: optional(formData, "purchase_date"),
      purchase_price: optional(formData, "purchase_price"),
      purchase_supplier: optional(formData, "purchase_supplier"),
      notes: optional(formData, "notes"),
    }),
  });
  revalidatePath("/fleet");
  redirect(`/fleet/vehicles/${vehicle.id}?branch=${branchId}`);
}

export async function addDocumentAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  const vehicleId = value(formData, "vehicle_id");
  let fileUrl: string | null = null;
  const file = formData.get("file");

  if (file instanceof File && file.size > 0) {
    const upload = new FormData();
    upload.append("branch_id", branchId);
    upload.append("file", file);
    const result = await nbrosApi<{ file_url: string }>("/api/v1/fleet/files", {
      method: "POST",
      body: upload,
    });
    fileUrl = result.file_url;
  }

  await nbrosApi("/api/v1/fleet/documents", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      vehicle_id: vehicleId,
      document_type: value(formData, "document_type"),
      document_number: optional(formData, "document_number"),
      issue_date: optional(formData, "issue_date"),
      expiry_date: optional(formData, "expiry_date"),
      file_url: fileUrl,
      is_required: true,
    }),
  });
  revalidatePath(`/fleet/vehicles/${vehicleId}`);
  redirect(`/fleet/vehicles/${vehicleId}?branch=${branchId}`);
}

export async function addServiceAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  const vehicleId = value(formData, "vehicle_id");
  await nbrosApi("/api/v1/fleet/services", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      vehicle_id: vehicleId,
      service_date: value(formData, "service_date"),
      mileage: Number(value(formData, "mileage")),
      service_type: value(formData, "service_type"),
      parts_used: optional(formData, "parts_used"),
      service_kit: optional(formData, "service_kit"),
      mechanic: optional(formData, "mechanic"),
      cost: optional(formData, "cost"),
      next_service_date: optional(formData, "next_service_date"),
      next_service_mileage: optional(formData, "next_service_mileage")
        ? Number(value(formData, "next_service_mileage"))
        : null,
    }),
  });
  revalidatePath(`/fleet/vehicles/${vehicleId}`);
  redirect(`/fleet/vehicles/${vehicleId}?branch=${branchId}`);
}

export async function addFaultAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  const vehicleId = value(formData, "vehicle_id");
  await nbrosApi("/api/v1/fleet/faults", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      vehicle_id: vehicleId,
      severity: value(formData, "severity"),
      description: value(formData, "description"),
    }),
  });
  revalidatePath(`/fleet/vehicles/${vehicleId}`);
  redirect(`/fleet/vehicles/${vehicleId}?branch=${branchId}`);
}

export async function addInspectionAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  const vehicleId = value(formData, "vehicle_id");
  await nbrosApi("/api/v1/fleet/inspections", {
    method: "POST",
    body: JSON.stringify({
      branch_id: branchId,
      vehicle_id: vehicleId,
      inspection_date: value(formData, "inspection_date"),
      status: value(formData, "status"),
      inspector: optional(formData, "inspector"),
      notes: optional(formData, "notes"),
      next_inspection_date: optional(formData, "next_inspection_date"),
    }),
  });
  revalidatePath(`/fleet/vehicles/${vehicleId}`);
  redirect(`/fleet/vehicles/${vehicleId}?branch=${branchId}`);
}
