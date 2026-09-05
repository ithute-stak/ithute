"use client"

import * as React from "react"
import { BookOpen, Loader2, Plus, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { addCurriculumOffering, CurriculumCatalog, CurriculumOffering, getCurriculum, getCurriculumCatalog, removeCurriculumOffering } from "@/api/academic"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"

export default function SubjectsPage() {
  const { workspace } = useSchoolWorkspace()
  const [items, setItems] = React.useState<CurriculumOffering[]>([])
  const [catalog, setCatalog] = React.useState<CurriculumCatalog | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [form, setForm] = React.useState({ grade_id: "", subject_id: "", daily_credit_hours: 1, weekly_credit_hours: 5, is_core: true })
  const canManage = workspace?.is_platform_admin || ["school_admin", "principal", "vice_principal"].includes(workspace?.role ?? "")

  const refresh = React.useCallback(async () => {
    setLoading(true)
    try {
      const [curriculum, nextCatalog] = await Promise.all([getCurriculum(), getCurriculumCatalog()])
      setItems(curriculum)
      setCatalog(nextCatalog)
      setForm((current) => ({ ...current, grade_id: current.grade_id || nextCatalog.grades[0]?.id || "", subject_id: current.subject_id || nextCatalog.subjects[0]?.id || "" }))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load curriculum")
    } finally { setLoading(false) }
  }, [])

  React.useEffect(() => { void refresh() }, [refresh])

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setSaving(true); setError(null)
    try { await addCurriculumOffering(form); await refresh() }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to add subject") }
    finally { setSaving(false) }
  }

  if (loading) return <div className="flex min-h-[50vh] items-center justify-center gap-3 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" />Loading curriculum…</div>

  const grouped = items.reduce<Record<string, CurriculumOffering[]>>((acc, item) => { (acc[item.grade ?? "Unassigned"] ??= []).push(item); return acc }, {})

  return <div className="space-y-6">
    <div className="rounded-2xl border bg-card p-6"><div className="flex items-center gap-2 text-sm text-muted-foreground"><BookOpen className="h-4 w-4" />School curriculum</div><h1 className="mt-2 text-3xl font-bold">Subjects by Grade</h1><p className="mt-2 text-sm text-muted-foreground">Choose which shared Tutor subjects {workspace?.school.name} teaches in each grade. Other schools are unaffected.</p></div>
    {error && <div className="rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</div>}
    {canManage && catalog && <Card><CardHeader><CardTitle>Add curriculum offering</CardTitle><CardDescription>Assign a catalog subject to one of this school's grades.</CardDescription></CardHeader><CardContent><form onSubmit={submit} className="grid gap-4 md:grid-cols-5"><div className="grid gap-1.5"><Label>Grade</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={form.grade_id} onChange={(e) => setForm((v) => ({ ...v, grade_id: e.target.value }))}>{catalog.grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select></div><div className="grid gap-1.5"><Label>Subject</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={form.subject_id} onChange={(e) => setForm((v) => ({ ...v, subject_id: e.target.value }))}>{catalog.subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div><div className="grid gap-1.5"><Label>Daily hours</Label><Input type="number" min={0} value={form.daily_credit_hours} onChange={(e) => setForm((v) => ({ ...v, daily_credit_hours: Number(e.target.value) }))} /></div><div className="grid gap-1.5"><Label>Weekly hours</Label><Input type="number" min={0} value={form.weekly_credit_hours} onChange={(e) => setForm((v) => ({ ...v, weekly_credit_hours: Number(e.target.value) }))} /></div><div className="flex items-end"><Button type="submit" disabled={saving || !form.grade_id || !form.subject_id}><Plus className="mr-2 h-4 w-4" />Add</Button></div></form></CardContent></Card>}
    <div className="grid gap-4 lg:grid-cols-2">{Object.entries(grouped).map(([grade, offerings]) => <Card key={grade}><CardHeader><CardTitle>{grade}</CardTitle><CardDescription>{offerings.length} subject{offerings.length === 1 ? "" : "s"}</CardDescription></CardHeader><CardContent className="space-y-2">{offerings.map((item) => <div key={item.id} className="flex items-center justify-between gap-4 rounded-lg border p-3"><div><p className="font-medium">{item.subject}</p><p className="text-xs text-muted-foreground">{item.is_core ? "Core" : "Elective"} · {item.weekly_credit_hours} hrs/week</p></div>{canManage && <Button variant="ghost" size="icon" onClick={async () => { await removeCurriculumOffering(item.id); await refresh() }}><Trash2 className="h-4 w-4" /></Button>}</div>)}</CardContent></Card>)}</div>
    {items.length === 0 && <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">No curriculum offerings yet. School administration can add the first subject above.</CardContent></Card>}
  </div>
}
