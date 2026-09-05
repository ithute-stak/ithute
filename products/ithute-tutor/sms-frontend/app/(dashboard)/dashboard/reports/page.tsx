"use client"

import * as React from "react"
import { BookOpenCheck, CalendarCheck2, Download, FileSpreadsheet, GraduationCap, Loader2, RefreshCw, UsersRound } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { downloadManagementReportExcel, downloadManagementReportPdf, getAttendanceTrend, getSchoolManagementReport, SchoolManagementReport, AttendanceTrendPoint } from "@/api/reports"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"

const money = (value: number, currency = "LSL") => new Intl.NumberFormat("en-LS", { style: "currency", currency }).format(value)

export default function ReportsPage() {
  const { workspace } = useSchoolWorkspace()
  const [report, setReport] = React.useState<SchoolManagementReport | null>(null)
  const [trend, setTrend] = React.useState<AttendanceTrendPoint[]>([])
  const [loading, setLoading] = React.useState(true)
  const [downloading, setDownloading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const refresh = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [nextReport, nextTrend] = await Promise.all([getSchoolManagementReport(), getAttendanceTrend(30)])
      setReport(nextReport)
      setTrend(nextTrend)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load school reports")
    } finally { setLoading(false) }
  }, [])

  React.useEffect(() => { void refresh() }, [refresh])

  const download = async (kind: "pdf" | "excel") => {
    setDownloading(true); setError(null)
    try { if (kind === "pdf") await downloadManagementReportPdf(); else await downloadManagementReportExcel() }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to download report") }
    finally { setDownloading(false) }
  }

  if (loading) return <div className="flex min-h-[55vh] items-center justify-center gap-3 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" />Building school report…</div>
  if (!report) return <div className="rounded-xl border p-6 text-sm text-muted-foreground">{error ?? "No report data available."}</div>

  const attendanceRecent = trend.slice(-7)
  const currency = workspace?.school.currency ?? "LSL"

  return <div className="space-y-6">
    <div className="flex flex-col gap-4 rounded-2xl border bg-card p-6 md:flex-row md:items-end md:justify-between">
      <div><p className="text-sm font-medium text-muted-foreground">Management reporting</p><h1 className="text-3xl font-bold tracking-tight">{workspace?.school.name} Reports</h1><p className="mt-2 text-sm text-muted-foreground">School-scoped academic, attendance, finance and staffing performance. Generated {report.generated_on}.</p></div>
      <div className="flex flex-wrap gap-2"><Button variant="outline" disabled={downloading} onClick={() => void download("pdf")}><Download className="mr-2 h-4 w-4" />PDF</Button><Button variant="outline" disabled={downloading} onClick={() => void download("excel")}><FileSpreadsheet className="mr-2 h-4 w-4" />Excel</Button><Button variant="outline" onClick={() => void refresh()}><RefreshCw className="mr-2 h-4 w-4" />Refresh</Button></div>
    </div>
    {error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <Card><CardHeader className="pb-2"><CardDescription>Active learners</CardDescription><CardTitle className="text-3xl">{report.people.active_students}</CardTitle></CardHeader><CardContent><GraduationCap className="h-5 w-5 text-muted-foreground" /></CardContent></Card>
      <Card><CardHeader className="pb-2"><CardDescription>Teachers / employees</CardDescription><CardTitle className="text-3xl">{report.people.teachers} / {report.people.employees}</CardTitle></CardHeader><CardContent><UsersRound className="h-5 w-5 text-muted-foreground" /></CardContent></Card>
      <Card><CardHeader className="pb-2"><CardDescription>Attendance rate</CardDescription><CardTitle className="text-3xl">{report.attendance.attendance_rate_percent == null ? "—" : `${report.attendance.attendance_rate_percent}%`}</CardTitle></CardHeader><CardContent><CalendarCheck2 className="h-5 w-5 text-muted-foreground" /></CardContent></Card>
      <Card><CardHeader className="pb-2"><CardDescription>Average published result</CardDescription><CardTitle className="text-3xl">{report.academics.average_published_score_percent == null ? "—" : `${report.academics.average_published_score_percent}%`}</CardTitle></CardHeader><CardContent><BookOpenCheck className="h-5 w-5 text-muted-foreground" /></CardContent></Card>
    </div>
    <div className="grid gap-6 xl:grid-cols-3">
      <Card className="xl:col-span-2"><CardHeader><CardTitle>Finance position</CardTitle><CardDescription>All figures belong only to this school workspace.</CardDescription></CardHeader><CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"><div className="rounded-xl border p-4"><p className="text-xs text-muted-foreground">Amount invoiced</p><p className="mt-1 text-xl font-semibold">{money(report.finance.amount_invoiced, currency)}</p></div><div className="rounded-xl border p-4"><p className="text-xs text-muted-foreground">Cash received</p><p className="mt-1 text-xl font-semibold">{money(report.finance.cash_received, currency)}</p></div><div className="rounded-xl border p-4"><p className="text-xs text-muted-foreground">Outstanding fees</p><p className="mt-1 text-xl font-semibold">{money(report.finance.outstanding_balance, currency)}</p></div><div className="rounded-xl border p-4"><p className="text-xs text-muted-foreground">Overdue invoices</p><p className="mt-1 text-xl font-semibold">{report.finance.overdue_invoices}</p></div><div className="rounded-xl border p-4"><p className="text-xs text-muted-foreground">Net payroll</p><p className="mt-1 text-xl font-semibold">{money(report.payroll.net_payroll, currency)}</p></div><div className="rounded-xl border p-4"><p className="text-xs text-muted-foreground">Payroll outstanding</p><p className="mt-1 text-xl font-semibold">{money(report.payroll.outstanding_balance, currency)}</p></div></CardContent></Card>
      <Card><CardHeader><CardTitle>Academic position</CardTitle><CardDescription>Current school academic cycle.</CardDescription></CardHeader><CardContent className="space-y-3 text-sm"><div className="flex justify-between gap-4"><span className="text-muted-foreground">Academic year</span><span className="font-medium">{report.academics.current_year ?? "Not set"}</span></div><div className="flex justify-between gap-4"><span className="text-muted-foreground">Current term</span><span className="font-medium">{report.academics.current_term ?? "Not set"}</span></div><div className="flex justify-between gap-4"><span className="text-muted-foreground">Assessments</span><span className="font-medium">{report.academics.assessments}</span></div><div className="flex justify-between gap-4"><span className="text-muted-foreground">Published</span><span className="font-medium">{report.academics.published_assessments}</span></div></CardContent></Card>
    </div>
    <Card><CardHeader><CardTitle>Recent attendance trend</CardTitle><CardDescription>Last recorded seven days from the 30-day attendance window.</CardDescription></CardHeader><CardContent>{attendanceRecent.length === 0 ? <p className="text-sm text-muted-foreground">No attendance records in the selected period.</p> : <div className="grid gap-3 md:grid-cols-7">{attendanceRecent.map((point) => <div key={point.date} className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">{point.date}</p><p className="mt-2 text-lg font-semibold">{point.rate_percent == null ? "—" : `${point.rate_percent}%`}</p><p className="text-xs text-muted-foreground">{point.present_or_late}/{point.records} present/late</p></div>)}</div>}</CardContent></Card>
  </div>
}
