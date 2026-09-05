"use client"

import * as React from "react"
import { Banknote, ClipboardList, Loader2, Plus, ShoppingCart, Users } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { addExpense, addSupplier, decideLeave, getExpenses, getLeaveRequests, getPurchaseOrders, getSuppliers, type Expense, type LeaveRequest, type PurchaseOrder, type Supplier } from "@/api/administration"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"

type Tab = "leave" | "suppliers" | "orders" | "expenses"

export default function AdministrationPage() {
  const { workspace } = useSchoolWorkspace()
  const [tab, setTab] = React.useState<Tab>("leave")
  const [leave, setLeave] = React.useState<LeaveRequest[]>([])
  const [suppliers, setSuppliers] = React.useState<Supplier[]>([])
  const [orders, setOrders] = React.useState<PurchaseOrder[]>([])
  const [expenses, setExpenses] = React.useState<Expense[]>([])
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [supplierForm, setSupplierForm] = React.useState({ name: "", email: "", phone: "" })
  const [expenseForm, setExpenseForm] = React.useState({ category: "Operations", description: "", amount: 0, expense_date: new Date().toISOString().slice(0, 10), reference: "" })

  const refresh = React.useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const results = await Promise.allSettled([getLeaveRequests(), getSuppliers(), getPurchaseOrders(), getExpenses()])
      if (results[0].status === "fulfilled") setLeave(results[0].value)
      if (results[1].status === "fulfilled") setSuppliers(results[1].value)
      if (results[2].status === "fulfilled") setOrders(results[2].value)
      if (results[3].status === "fulfilled") setExpenses(results[3].value)
      if (results.every((result) => result.status === "rejected")) throw new Error("Your role does not have access to administration data")
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to load administration") }
    finally { setLoading(false) }
  }, [])
  React.useEffect(() => { void refresh() }, [workspace?.school.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (action: () => Promise<unknown>) => { setSaving(true); setError(null); try { await action(); await refresh() } catch (err) { setError(err instanceof Error ? err.message : "Unable to save") } finally { setSaving(false) } }

  if (loading) return <div className="flex min-h-[55vh] items-center justify-center gap-3 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" />Loading administration…</div>

  const tabs: Array<[Tab, string, React.ReactNode]> = [["leave", "HR Leave", <Users key="u" className="h-4 w-4" />], ["suppliers", "Suppliers", <ShoppingCart key="s" className="h-4 w-4" />], ["orders", "Purchase Orders", <ClipboardList key="o" className="h-4 w-4" />], ["expenses", "Expenses", <Banknote key="e" className="h-4 w-4" />]]

  return <div className="space-y-6"><div className="rounded-2xl border bg-card p-6"><h1 className="text-3xl font-bold tracking-tight">Administration</h1><p className="mt-2 text-sm text-muted-foreground">HR leave, suppliers, procurement and operating expenses remain isolated inside this school workspace.</p></div>{error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}<div className="flex flex-wrap gap-2">{tabs.map(([key, title, icon]) => <Button key={key} variant={tab === key ? "default" : "outline"} onClick={() => setTab(key)}>{icon}<span className="ml-2">{title}</span></Button>)}</div>

  {tab === "leave" && <Card><CardHeader><CardTitle>Leave requests</CardTitle><CardDescription>HR/principal decisions are auditable by reviewer and timestamp.</CardDescription></CardHeader><CardContent className="space-y-3">{leave.map((item) => <div key={item.id} className="flex flex-col gap-3 rounded-xl border p-4 md:flex-row md:items-center md:justify-between"><div><div className="font-medium">{item.leave_type}</div><div className="text-xs text-muted-foreground">{item.start_date} → {item.end_date} · {item.status}</div></div>{item.status === "pending" && <div className="flex gap-2"><Button size="sm" disabled={saving} onClick={() => void run(() => decideLeave(item.id, "approved"))}>Approve</Button><Button size="sm" variant="destructive" disabled={saving} onClick={() => void run(() => decideLeave(item.id, "rejected"))}>Reject</Button></div>}</div>)}</CardContent></Card>}

  {tab === "suppliers" && <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]"><Card><CardHeader><CardTitle>Supplier register</CardTitle></CardHeader><CardContent className="space-y-3">{suppliers.map((item) => <div key={item.id} className="rounded-lg border p-3"><div className="font-medium">{item.name}</div><div className="text-xs text-muted-foreground">{item.phone || item.email || "No contact"}</div></div>)}</CardContent></Card><Card><CardHeader><CardTitle>Add supplier</CardTitle></CardHeader><CardContent className="space-y-3"><div className="grid gap-1.5"><Label>Name</Label><Input value={supplierForm.name} onChange={(e) => setSupplierForm((v) => ({ ...v, name: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Phone</Label><Input value={supplierForm.phone} onChange={(e) => setSupplierForm((v) => ({ ...v, phone: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Email</Label><Input value={supplierForm.email} onChange={(e) => setSupplierForm((v) => ({ ...v, email: e.target.value }))} /></div><Button disabled={saving || !supplierForm.name} onClick={() => void run(() => addSupplier(supplierForm))}><Plus className="mr-2 h-4 w-4" />Add supplier</Button></CardContent></Card></div>}

  {tab === "orders" && <Card><CardHeader><CardTitle>Purchase orders</CardTitle></CardHeader><CardContent className="space-y-3">{orders.map((item) => <div key={item.id} className="rounded-lg border p-3"><div className="flex justify-between gap-3"><div className="font-medium">{item.order_number}</div><div className="font-semibold">M {Number(item.total_amount).toLocaleString()}</div></div><div className="mt-1 text-xs text-muted-foreground">{item.status}</div></div>)}{orders.length === 0 && <div className="text-sm text-muted-foreground">No purchase orders yet.</div>}</CardContent></Card>}

  {tab === "expenses" && <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]"><Card><CardHeader><CardTitle>Expense register</CardTitle></CardHeader><CardContent className="space-y-3">{expenses.map((item) => <div key={item.id} className="rounded-lg border p-3"><div className="flex justify-between gap-3"><div className="font-medium">{item.description}</div><div className="font-semibold">M {Number(item.amount).toLocaleString()}</div></div><div className="mt-1 text-xs text-muted-foreground">{item.category} · {item.expense_date}</div></div>)}</CardContent></Card><Card><CardHeader><CardTitle>Record expense</CardTitle></CardHeader><CardContent className="space-y-3"><div className="grid gap-1.5"><Label>Category</Label><Input value={expenseForm.category} onChange={(e) => setExpenseForm((v) => ({ ...v, category: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Description</Label><Input value={expenseForm.description} onChange={(e) => setExpenseForm((v) => ({ ...v, description: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Amount (M)</Label><Input type="number" min={0} step="0.01" value={expenseForm.amount} onChange={(e) => setExpenseForm((v) => ({ ...v, amount: Number(e.target.value) }))} /></div><Button disabled={saving || !expenseForm.description} onClick={() => void run(() => addExpense(expenseForm))}>Record expense</Button></CardContent></Card></div>}
  </div>
}
