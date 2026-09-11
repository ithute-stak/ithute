"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { nbrosApi } from "@/lib/backend";

function value(formData: FormData, key: string): string { return String(formData.get(key) ?? "").trim(); }

export async function createInventoryItemAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/fleet/inventory/items", { method: "POST", body: JSON.stringify({ branch_id: branchId, sku: value(formData, "sku"), name: value(formData, "name"), category: value(formData, "category") || "service_kit", opening_quantity: Number(value(formData, "opening_quantity") || 0), reorder_level: Number(value(formData, "reorder_level") || 0), unit: value(formData, "unit") || "unit" }) });
  revalidatePath("/fleet/inventory");
  redirect(`/fleet/inventory?branch=${branchId}`);
}

export async function recordInventoryMovementAction(formData: FormData) {
  const branchId = value(formData, "branch_id");
  await nbrosApi("/api/v1/fleet/inventory/movements", { method: "POST", body: JSON.stringify({ branch_id: branchId, item_id: value(formData, "item_id"), quantity_delta: Number(value(formData, "quantity_delta")), movement_type: value(formData, "movement_type"), reference_type: value(formData, "reference_type") || null, reference_id: value(formData, "reference_id") || null, notes: value(formData, "notes") || null }) });
  revalidatePath("/fleet/inventory");
  redirect(`/fleet/inventory?branch=${branchId}`);
}
