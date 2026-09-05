"use client"

import * as React from "react"
import { CalendarDays, Loader2, Plus } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { createTimetableEntry, getAcademicOverview, getAcademicTerms, getCurriculum, getTeachingAssignments, getTimetable, TimetableEntry, TeachingAssignment } from "@/api/academic"
import { useAppData } from "@/provider/dataProvider"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

export default function TimetablePage() {
  const { workspace } = useSchoolWorkspace()
  const { teachers, classes } = useAppData()
  const [entries, setEntries] = React.useState<TimetableEntry[]>([])
  const [assignments, setAssignments] = React.useState<TeachingAssignment[]>([])
  const [terms, setTerms] = React.useState<{id:string; name:string; academic_year_id:string}[]>([])
  const [subjects, setSubjects] = React.useState<Record<string, string>>({})
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [form, setForm] = React.useState({ academic_year_id: "", term_id: "", teaching_assignment_id: "", day_of_week: 1, start_time: "08:00", end_time: "09:00", room: "", notes: "" })
  const canManage = workspace?.is_platform_admin || ["school_admin", "principal", "vice_principal"].includes(workspace?.role ?? "")

  const refresh = React.useCallback(async () => {
    setLoading(true)
    try {
      const [overview, nextTerms, nextAssignments, nextEntries, curriculum] = await Promise.all([getAcademicOverview(), getAcademicTerms(), getTeachingAssignments(), getTimetable(), getCurriculum()])
      setTerms(nextTerms); setAssignments(nextAssignments); setEntries(nextEntries)
      setSubjects(Object.fromEntries(curriculum.map((item) => [item.subject_id, item.subject ?? item.subject_id])))
      const term = overview.current_term ?? nextTerms[0]
      setForm((v) => ({ ...v, academic_year_id: v.academic_year_id || term?.academic_year_id || overview.current_year?.id || "", term_id: v.term_id || term?.id || "", teaching_assignment_id: v.teaching_assignment_id || nextAssignments[0]?.id || "" }))
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to load timetable") }
    finally { setLoading(false) }
  }, [])
  React.useEffect(() => { void refresh() }, [refresh])

  const assignmentLabel = (id: string) => {
    const a = assignments.find((item) => item.id === id)
    if (!a) return id
    const teacher = teachers.find((item) => item.id === a.teacher_id)?.user.username ?? "Teacher"
    const classroom = classes.find((item) => item.id === a.class_id)?.name ?? "Class"
    return `${teacher} · ${classroom} · ${subjects[a.subject_id] ?? "Subject"}`
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setSaving(true); setError(null)
    try { await createTimetableEntry({ ...form, room: form.room || null, notes: form.notes || null }); await refresh() }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to add timetable period") }
    finally { setSaving(false) }
  }

  if (loading) return <div className="flex min-h-[50vh] items-center justify-center gap-3 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" />Loading timetable…</div>

  return <div className="space-y-6">
    <div className="rounded-2xl border bg-card p-6"><div className="flex items-center gap-2 text-sm text-muted-foreground"><CalendarDays className="h-4 w-4" />Academic operations</div><h1 className="mt-2 text-3xl font-bold">School Timetable</h1><p className="mt-2 text-sm text-muted-foreground">Tutor blocks overlapping periods for both the same teacher and the same class.</p></div>
    {error && <div className="rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</div>}
    {canManage && <Card><CardHeader><CardTitle>Add timetable period</CardTitle><CardDescription>Teaching assignments must be configured before scheduling.</CardDescription></CardHeader><CardContent><form onSubmit={submit} className="grid gap-4 md:grid-cols-4"><div className="grid gap-1.5 md:col-span-2"><Label>Teaching assignment</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={form.teaching_assignment_id} onChange={(e) => setForm((v) => ({...v, teaching_assignment_id:e.target.value}))}>{assignments.map((a) => <option key={a.id} value={a.id}>{assignmentLabel(a.id)}</option>)}</select></div><div className="grid gap-1.5"><Label>Term</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={form.term_id} onChange={(e) => { const t=terms.find((x)=>x.id===e.target.value); setForm((v)=>({...v,term_id:e.target.value,academic_year_id:t?.academic_year_id??v.academic_year_id})) }}>{terms.map((t)=><option key={t.id} value={t.id}>{t.name}</option>)}</select></div><div className="grid gap-1.5"><Label>Day</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={form.day_of_week} onChange={(e)=>setForm((v)=>({...v,day_of_week:Number(e.target.value)}))}>{DAYS.map((day,index)=><option key={day} value={index+1}>{day}</option>)}</select></div><div className="grid gap-1.5"><Label>Start</Label><Input type="time" value={form.start_time} onChange={(e)=>setForm((v)=>({...v,start_time:e.target.value}))}/></div><div className="grid gap-1.5"><Label>End</Label><Input type="time" value={form.end_time} onChange={(e)=>setForm((v)=>({...v,end_time:e.target.value}))}/></div><div className="grid gap-1.5"><Label>Room</Label><Input value={form.room} onChange={(e)=>setForm((v)=>({...v,room:e.target.value}))}/></div><div className="flex items-end"><Button type="submit" disabled={saving || !form.term_id || !form.teaching_assignment_id}><Plus className="mr-2 h-4 w-4"/>Add period</Button></div></form></CardContent></Card>}
    <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">{DAYS.map((day,index)=>{const dayEntries=entries.filter((e)=>e.day_of_week===index+1);return <Card key={day}><CardHeader><CardTitle>{day}</CardTitle><CardDescription>{dayEntries.length} period{dayEntries.length===1?"":"s"}</CardDescription></CardHeader><CardContent className="space-y-2">{dayEntries.length===0?<p className="text-sm text-muted-foreground">No periods.</p>:dayEntries.map((entry)=><div key={entry.id} className="rounded-lg border p-3"><p className="font-medium">{entry.start_time.slice(0,5)}–{entry.end_time.slice(0,5)}</p><p className="text-sm">{assignmentLabel(entry.teaching_assignment_id)}</p>{entry.room&&<p className="text-xs text-muted-foreground">Room: {entry.room}</p>}</div>)}</CardContent></Card>})}</div>
  </div>
}
