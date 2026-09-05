import api from "@/lib/axios-setup"

export type LeaveRequest = { id: string; employee_id: string; leave_type: string; start_date: string; end_date: string; reason?: string | null; status: string; review_note?: string | null }
export type Supplier = { id: string; name: string; email?: string | null; phone?: string | null; address?: string | null; tax_number?: string | null; status: string }
export type PurchaseOrder = { id: string; order_number: string; supplier_id?: string | null; items: Array<Record<string, unknown>>; subtotal: number | string; tax_amount: number | string; total_amount: number | string; status: string }
export type Expense = { id: string; category: string; description: string; amount: number | string; expense_date: string; reference?: string | null; status: string }

export async function getLeaveRequests() { return (await api.get<LeaveRequest[]>("/api/administration/leave", { withCredentials: true })).data }
export async function decideLeave(id: string, status: "approved" | "rejected" | "cancelled", review_note?: string) { return (await api.put<LeaveRequest>(`/api/administration/leave/${id}/decision`, { status, review_note: review_note || null }, { withCredentials: true })).data }
export async function getSuppliers() { return (await api.get<Supplier[]>("/api/administration/suppliers", { withCredentials: true })).data }
export async function addSupplier(payload: { name: string; email?: string; phone?: string; address?: string; tax_number?: string }) { return (await api.post<Supplier>("/api/administration/suppliers", payload, { withCredentials: true })).data }
export async function getPurchaseOrders() { return (await api.get<PurchaseOrder[]>("/api/administration/purchase-orders", { withCredentials: true })).data }
export async function getExpenses() { return (await api.get<Expense[]>("/api/administration/expenses", { withCredentials: true })).data }
export async function addExpense(payload: { category: string; description: string; amount: number; expense_date: string; reference?: string }) { return (await api.post<Expense>("/api/administration/expenses", payload, { withCredentials: true })).data }
