import api from "@/lib/axios-setup"

export type CalendarEvent = { id: string; title: string; description?: string | null; category: string; starts_at: string; ends_at?: string | null; audience: string }
export type LibraryBook = { id: string; title: string; author?: string | null; isbn?: string | null; category?: string | null; copies_total: number; copies_available: number }
export type TransportRoute = { id: string; name: string; driver_name?: string | null; driver_phone?: string | null; vehicle_registration?: string | null; stops: Array<Record<string, unknown>>; is_active: boolean }
export type InventoryAsset = { id: string; asset_code: string; name: string; category?: string | null; quantity: number; location?: string | null; status: string }

export async function getCalendar() { return (await api.get<CalendarEvent[]>("/api/operations/calendar", { withCredentials: true })).data }
export async function addCalendarEvent(payload: Omit<CalendarEvent, "id">) { return (await api.post<CalendarEvent>("/api/operations/calendar", payload, { withCredentials: true })).data }
export async function getLibraryBooks() { return (await api.get<LibraryBook[]>("/api/operations/library/books", { withCredentials: true })).data }
export async function addLibraryBook(payload: { title: string; author?: string; isbn?: string; category?: string; copies_total: number }) { return (await api.post<LibraryBook>("/api/operations/library/books", payload, { withCredentials: true })).data }
export async function getTransportRoutes() { return (await api.get<TransportRoute[]>("/api/operations/transport/routes", { withCredentials: true })).data }
export async function addTransportRoute(payload: { name: string; driver_name?: string; driver_phone?: string; vehicle_registration?: string; stops?: Array<Record<string, unknown>> }) { return (await api.post<TransportRoute>("/api/operations/transport/routes", payload, { withCredentials: true })).data }
export async function getAssets() { return (await api.get<InventoryAsset[]>("/api/operations/assets", { withCredentials: true })).data }
export async function addAsset(payload: { asset_code: string; name: string; category?: string; quantity: number; location?: string }) { return (await api.post<InventoryAsset>("/api/operations/assets", payload, { withCredentials: true })).data }
