"use client"

import * as React from "react"
import { BookOpen, Bus, CalendarDays, Loader2, Package, Plus } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { addAsset, addCalendarEvent, addLibraryBook, addTransportRoute, getAssets, getCalendar, getLibraryBooks, getTransportRoutes, type CalendarEvent, type InventoryAsset, type LibraryBook, type TransportRoute } from "@/api/operations"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"

type Tab = "calendar" | "library" | "transport" | "assets"

export default function OperationsPage() {
  const { workspace } = useSchoolWorkspace()
  const [tab, setTab] = React.useState<Tab>("calendar")
  const [events, setEvents] = React.useState<CalendarEvent[]>([])
  const [books, setBooks] = React.useState<LibraryBook[]>([])
  const [routes, setRoutes] = React.useState<TransportRoute[]>([])
  const [assets, setAssets] = React.useState<InventoryAsset[]>([])
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [eventForm, setEventForm] = React.useState({ title: "", description: "", category: "school", starts_at: "", ends_at: "", audience: "all" })
  const [bookForm, setBookForm] = React.useState({ title: "", author: "", isbn: "", category: "", copies_total: 1 })
  const [routeForm, setRouteForm] = React.useState({ name: "", driver_name: "", driver_phone: "", vehicle_registration: "" })
  const [assetForm, setAssetForm] = React.useState({ asset_code: "", name: "", category: "", quantity: 1, location: "" })

  const refresh = React.useCallback(async () => {
    setLoading(true); setError(null)
    try { const [a, b, c, d] = await Promise.all([getCalendar(), getLibraryBooks(), getTransportRoutes(), getAssets()]); setEvents(a); setBooks(b); setRoutes(c); setAssets(d) }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to load school operations") }
    finally { setLoading(false) }
  }, [])
  React.useEffect(() => { void refresh() }, [workspace?.school.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (action: () => Promise<unknown>) => { setSaving(true); setError(null); try { await action(); await refresh() } catch (err) { setError(err instanceof Error ? err.message : "Unable to save") } finally { setSaving(false) } }

  if (loading) return <div className="flex min-h-[55vh] items-center justify-center gap-3 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" />Loading operations…</div>

  const tabs: Array<[Tab, string, React.ReactNode, number]> = [["calendar", "Calendar", <CalendarDays key="c" className="h-4 w-4" />, events.length], ["library", "Library", <BookOpen key="b" className="h-4 w-4" />, books.length], ["transport", "Transport", <Bus key="t" className="h-4 w-4" />, routes.length], ["assets", "Assets", <Package key="a" className="h-4 w-4" />, assets.length]]

  return <div className="space-y-6"><div className="rounded-2xl border bg-card p-6"><h1 className="text-3xl font-bold tracking-tight">School Operations</h1><p className="mt-2 text-sm text-muted-foreground">One operational workspace for calendar, library, learner transport and school assets.</p></div>{error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}<div className="flex flex-wrap gap-2">{tabs.map(([key, label, icon, count]) => <Button key={key} variant={tab === key ? "default" : "outline"} onClick={() => setTab(key)}>{icon}<span className="ml-2">{label} ({count})</span></Button>)}</div>

  {tab === "calendar" && <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]"><Card><CardHeader><CardTitle>School calendar</CardTitle></CardHeader><CardContent className="space-y-3">{events.map((item) => <div key={item.id} className="rounded-lg border p-3"><div className="font-medium">{item.title}</div><div className="mt-1 text-xs text-muted-foreground">{new Date(item.starts_at).toLocaleString()} · {item.audience}</div></div>)}{events.length === 0 && <div className="text-sm text-muted-foreground">No events.</div>}</CardContent></Card><Card><CardHeader><CardTitle>Add event</CardTitle></CardHeader><CardContent className="space-y-3"><div className="grid gap-1.5"><Label>Title</Label><Input value={eventForm.title} onChange={(e) => setEventForm((v) => ({ ...v, title: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Starts</Label><Input type="datetime-local" value={eventForm.starts_at} onChange={(e) => setEventForm((v) => ({ ...v, starts_at: e.target.value }))} /></div><Button disabled={saving || !eventForm.title || !eventForm.starts_at} onClick={() => void run(() => addCalendarEvent({ ...eventForm, starts_at: new Date(eventForm.starts_at).toISOString(), ends_at: eventForm.ends_at ? new Date(eventForm.ends_at).toISOString() : null }))}><Plus className="mr-2 h-4 w-4" />Add event</Button></CardContent></Card></div>}

  {tab === "library" && <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]"><Card><CardHeader><CardTitle>Library catalogue</CardTitle></CardHeader><CardContent className="space-y-3">{books.map((item) => <div key={item.id} className="rounded-lg border p-3"><div className="font-medium">{item.title}</div><div className="mt-1 text-xs text-muted-foreground">{item.author || "Unknown author"} · {item.copies_available}/{item.copies_total} available</div></div>)}</CardContent></Card><Card><CardHeader><CardTitle>Add book</CardTitle></CardHeader><CardContent className="space-y-3"><div className="grid gap-1.5"><Label>Title</Label><Input value={bookForm.title} onChange={(e) => setBookForm((v) => ({ ...v, title: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Author</Label><Input value={bookForm.author} onChange={(e) => setBookForm((v) => ({ ...v, author: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Copies</Label><Input type="number" min={0} value={bookForm.copies_total} onChange={(e) => setBookForm((v) => ({ ...v, copies_total: Number(e.target.value) }))} /></div><Button disabled={saving || !bookForm.title} onClick={() => void run(() => addLibraryBook(bookForm))}>Add book</Button></CardContent></Card></div>}

  {tab === "transport" && <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]"><Card><CardHeader><CardTitle>Transport routes</CardTitle></CardHeader><CardContent className="space-y-3">{routes.map((item) => <div key={item.id} className="rounded-lg border p-3"><div className="font-medium">{item.name}</div><div className="mt-1 text-xs text-muted-foreground">{item.driver_name || "Driver not assigned"} · {item.vehicle_registration || "Vehicle not assigned"}</div></div>)}</CardContent></Card><Card><CardHeader><CardTitle>Add route</CardTitle></CardHeader><CardContent className="space-y-3"><div className="grid gap-1.5"><Label>Route name</Label><Input value={routeForm.name} onChange={(e) => setRouteForm((v) => ({ ...v, name: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Driver</Label><Input value={routeForm.driver_name} onChange={(e) => setRouteForm((v) => ({ ...v, driver_name: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Vehicle</Label><Input value={routeForm.vehicle_registration} onChange={(e) => setRouteForm((v) => ({ ...v, vehicle_registration: e.target.value }))} /></div><Button disabled={saving || !routeForm.name} onClick={() => void run(() => addTransportRoute(routeForm))}>Add route</Button></CardContent></Card></div>}

  {tab === "assets" && <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]"><Card><CardHeader><CardTitle>Asset register</CardTitle></CardHeader><CardContent className="space-y-3">{assets.map((item) => <div key={item.id} className="rounded-lg border p-3"><div className="font-medium">{item.name}</div><div className="mt-1 text-xs text-muted-foreground">{item.asset_code} · Qty {item.quantity} · {item.location || "No location"}</div></div>)}</CardContent></Card><Card><CardHeader><CardTitle>Add asset</CardTitle></CardHeader><CardContent className="space-y-3"><div className="grid gap-1.5"><Label>Asset code</Label><Input value={assetForm.asset_code} onChange={(e) => setAssetForm((v) => ({ ...v, asset_code: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Name</Label><Input value={assetForm.name} onChange={(e) => setAssetForm((v) => ({ ...v, name: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Quantity</Label><Input type="number" min={0} value={assetForm.quantity} onChange={(e) => setAssetForm((v) => ({ ...v, quantity: Number(e.target.value) }))} /></div><Button disabled={saving || !assetForm.asset_code || !assetForm.name} onClick={() => void run(() => addAsset(assetForm))}>Add asset</Button></CardContent></Card></div>}
  </div>
}
