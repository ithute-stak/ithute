"use client"

import * as React from "react"
import Link from "next/link"
import {
  BookOpen,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  GraduationCap,
  Loader2,
  Plus,
  UsersRound,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  AcademicOverview,
  AcademicTerm,
  AcademicYear,
  createAcademicTerm,
  createAcademicYear,
  getAcademicOverview,
  getAcademicTerms,
  getAcademicYears,
  getAssessments,
  getTeachingAssignments,
  getTimetable,
} from "@/api/academic"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"

function formatDate(value?: string | null) {
  if (!value) return "Not set"
  return new Intl.DateTimeFormat("en-LS", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(`${value}T00:00:00`))
}

export default function AcademicCenterPage() {
  const { workspace } = useSchoolWorkspace()
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [overview, setOverview] = React.useState<AcademicOverview | null>(null)
  const [years, setYears] = React.useState<AcademicYear[]>([])
  const [terms, setTerms] = React.useState<AcademicTerm[]>([])
  const [timetableCount, setTimetableCount] = React.useState(0)
  const [assignmentCount, setAssignmentCount] = React.useState(0)
  const [assessmentCount, setAssessmentCount] = React.useState(0)
  const [yearForm, setYearForm] = React.useState({ name: `${new Date().getFullYear()}`, start_date: "", end_date: "" })
  const [termForm, setTermForm] = React.useState({ academic_year_id: "", name: "Term 1", sequence: 1, start_date: "", end_date: "" })

  const canManage = workspace?.is_platform_admin || ["school_admin", "principal", "vice_principal"].includes(workspace?.role ?? "")

  const refresh = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [nextOverview, nextYears, nextTerms, assignments, timetable, assessments] = await Promise.all([
        getAcademicOverview(),
        getAcademicYears(),
        getAcademicTerms(),
        getTeachingAssignments(),
        getTimetable(),
        getAssessments(),
      ])
      setOverview(nextOverview)
      setYears(nextYears)
      setTerms(nextTerms)
      setAssignmentCount(assignments.length)
      setTimetableCount(timetable.length)
      setAssessmentCount(assessments.length)
      setTermForm((current) => ({
        ...current,
        academic_year_id: current.academic_year_id || nextOverview.current_year?.id || nextYears[0]?.id || "",
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load academic data")
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => { void refresh() }, [refresh])

  const submitYear = async (event: React.FormEvent) => {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await createAcademicYear({ ...yearForm, is_current: years.length === 0 })
      setYearForm({ name: `${new Date().getFullYear()}`, start_date: "", end_date: "" })
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create academic year")
    } finally {
      setSaving(false)
    }
  }

  const submitTerm = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!termForm.academic_year_id) return
    setSaving(true)
    setError(null)
    try {
      await createAcademicTerm({ ...termForm, is_current: !overview?.current_term })
      setTermForm((current) => ({ ...current, name: `Term ${current.sequence + 1}`, sequence: current.sequence + 1, start_date: "", end_date: "" }))
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create academic term")
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="flex min-h-[55vh] items-center justify-center gap-3 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" />Loading academic workspace…</div>
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 rounded-2xl border bg-card p-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground"><GraduationCap className="h-4 w-4" />Academic operations</div>
          <h1 className="text-3xl font-bold tracking-tight">{workspace?.school.name ?? "School"} Academic Center</h1>
          <p className="mt-2 max-w-3xl text-sm text-muted-foreground">Run the academic calendar, teaching assignments, timetable, assessments, marks and report-card workflow inside this school workspace.</p>
        </div>
        <Button variant="outline" onClick={() => void refresh()}>Refresh</Button>
      </div>

      {error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <Card><CardHeader className="pb-2"><CardDescription>Current year</CardDescription><CardTitle className="text-xl">{overview?.current_year?.name ?? "Not configured"}</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground">{overview?.current_year ? `${formatDate(overview.current_year.start_date)} – ${formatDate(overview.current_year.end_date)}` : "Create an academic year below"}</CardContent></Card>
        <Card><CardHeader className="pb-2"><CardDescription>Current term</CardDescription><CardTitle className="text-xl">{overview?.current_term?.name ?? "Not configured"}</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground">{overview?.current_term ? `${formatDate(overview.current_term.start_date)} – ${formatDate(overview.current_term.end_date)}` : "Create a term below"}</CardContent></Card>
        <Card><CardHeader className="pb-2"><CardDescription>Teaching assignments</CardDescription><CardTitle className="text-2xl">{assignmentCount}</CardTitle></CardHeader><CardContent><UsersRound className="h-4 w-4 text-muted-foreground" /></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardDescription>Timetable periods</CardDescription><CardTitle className="text-2xl">{timetableCount}</CardTitle></CardHeader><CardContent><CalendarDays className="h-4 w-4 text-muted-foreground" /></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardDescription>Assessments</CardDescription><CardTitle className="text-2xl">{assessmentCount}</CardTitle></CardHeader><CardContent><ClipboardList className="h-4 w-4 text-muted-foreground" /></CardContent></Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        {[
          ["Curriculum", "Classes, grades and subjects offered by this school.", "/dashboard/subjects", BookOpen],
          ["Teaching load", "Assign teachers to classes and subjects for the academic period.", "/dashboard/teachers/schedules", UsersRound],
          ["Timetable", "Build and review school, class and teacher schedules.", "/dashboard/timetable", CalendarDays],
          ["Assessment & results", "Create assessments, capture marks and publish results.", "/dashboard/exams", ClipboardList],
        ].map(([title, description, href, Icon]) => {
          const IconComponent = Icon as typeof BookOpen
          return <Link key={String(title)} href={String(href)}><Card className="h-full transition-colors hover:bg-muted/40"><CardHeader><IconComponent className="mb-2 h-5 w-5" /><CardTitle className="text-base">{String(title)}</CardTitle><CardDescription>{String(description)}</CardDescription></CardHeader></Card></Link>
        })}
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Academic years</CardTitle><CardDescription>Each school controls its own academic calendar. Closing a year preserves its records.</CardDescription></CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              {years.length === 0 && <p className="text-sm text-muted-foreground">No academic years yet.</p>}
              {years.map((year) => <div key={year.id} className="flex items-center justify-between rounded-lg border p-3"><div><div className="flex items-center gap-2 font-medium">{year.name}{year.is_current && <CheckCircle2 className="h-4 w-4" />}</div><div className="text-xs text-muted-foreground">{formatDate(year.start_date)} – {formatDate(year.end_date)}</div></div><span className="text-xs text-muted-foreground">{year.is_closed ? "Closed" : year.is_current ? "Current" : "Open"}</span></div>)}
            </div>
            {canManage && <form onSubmit={submitYear} className="grid gap-3 border-t pt-4 sm:grid-cols-3"><div className="grid gap-1.5"><Label>Year name</Label><Input value={yearForm.name} onChange={(e) => setYearForm((v) => ({ ...v, name: e.target.value }))} required /></div><div className="grid gap-1.5"><Label>Start date</Label><Input type="date" value={yearForm.start_date} onChange={(e) => setYearForm((v) => ({ ...v, start_date: e.target.value }))} required /></div><div className="grid gap-1.5"><Label>End date</Label><Input type="date" value={yearForm.end_date} onChange={(e) => setYearForm((v) => ({ ...v, end_date: e.target.value }))} required /></div><div className="sm:col-span-3"><Button type="submit" disabled={saving}><Plus className="mr-2 h-4 w-4" />Add academic year</Button></div></form>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Terms</CardTitle><CardDescription>Terms belong to a school academic year and drive timetable, attendance and result reporting.</CardDescription></CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              {terms.length === 0 && <p className="text-sm text-muted-foreground">No academic terms yet.</p>}
              {terms.map((term) => <div key={term.id} className="flex items-center justify-between rounded-lg border p-3"><div><div className="flex items-center gap-2 font-medium">{term.name}{term.is_current && <CheckCircle2 className="h-4 w-4" />}</div><div className="text-xs text-muted-foreground">{formatDate(term.start_date)} – {formatDate(term.end_date)}</div></div><span className="text-xs text-muted-foreground">#{term.sequence}</span></div>)}
            </div>
            {canManage && years.length > 0 && <form onSubmit={submitTerm} className="grid gap-3 border-t pt-4 sm:grid-cols-2"><div className="grid gap-1.5 sm:col-span-2"><Label>Academic year</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={termForm.academic_year_id} onChange={(e) => setTermForm((v) => ({ ...v, academic_year_id: e.target.value }))}>{years.filter((year) => !year.is_closed).map((year) => <option key={year.id} value={year.id}>{year.name}</option>)}</select></div><div className="grid gap-1.5"><Label>Term name</Label><Input value={termForm.name} onChange={(e) => setTermForm((v) => ({ ...v, name: e.target.value }))} required /></div><div className="grid gap-1.5"><Label>Sequence</Label><Input type="number" min={1} value={termForm.sequence} onChange={(e) => setTermForm((v) => ({ ...v, sequence: Number(e.target.value) }))} required /></div><div className="grid gap-1.5"><Label>Start date</Label><Input type="date" value={termForm.start_date} onChange={(e) => setTermForm((v) => ({ ...v, start_date: e.target.value }))} required /></div><div className="grid gap-1.5"><Label>End date</Label><Input type="date" value={termForm.end_date} onChange={(e) => setTermForm((v) => ({ ...v, end_date: e.target.value }))} required /></div><div className="sm:col-span-2"><Button type="submit" disabled={saving}><Plus className="mr-2 h-4 w-4" />Add term</Button></div></form>}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
