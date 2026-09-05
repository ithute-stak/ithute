import api from "@/lib/axios-setup"

export type SchoolManagementReport = {
  school_id: string
  generated_on: string
  people: { active_students: number; teachers: number; employees: number }
  academics: { current_year: string | null; current_term: string | null; assessments: number; published_assessments: number; average_published_score_percent: number | null }
  attendance: { records: number; present_or_late: number; absent: number; attendance_rate_percent: number | null }
  finance: { invoices_count: number; amount_invoiced: number; amount_allocated_paid: number; outstanding_balance: number; cash_received: number; overdue_invoices: number }
  payroll: { net_payroll: number; amount_paid: number; outstanding_balance: number }
}

export type AttendanceTrendPoint = { date: string; records: number; present_or_late: number; rate_percent: number | null }

export async function getSchoolManagementReport() { return (await api.get<SchoolManagementReport>("/api/reports/overview", { withCredentials: true })).data }
export async function getAttendanceTrend(days = 30) { return (await api.get<AttendanceTrendPoint[]>("/api/reports/attendance/trend", { params: { days }, withCredentials: true })).data }

async function downloadReport(path: string, filename: string) {
  const response = await api.get(path, { withCredentials: true, responseType: "blob" })
  const url = URL.createObjectURL(response.data)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export async function downloadManagementReportPdf() { return downloadReport("/api/reports/export/management.pdf", "ithute-tutor-management-report.pdf") }
export async function downloadManagementReportExcel() { return downloadReport("/api/reports/export/management.xlsx", "ithute-tutor-management-report.xlsx") }
