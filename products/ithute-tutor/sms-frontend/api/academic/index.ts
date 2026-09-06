import api from "@/lib/axios-setup"

export type AcademicYear = { id: string; school_id: string; name: string; start_date: string; end_date: string; is_current: boolean; is_closed: boolean }
export type AcademicTerm = { id: string; school_id: string; academic_year_id: string; name: string; sequence: number; start_date: string; end_date: string; is_current: boolean; is_closed: boolean }
export type TeachingAssignment = { id: string; school_id: string; academic_year_id: string; term_id?: string | null; teacher_id: string; class_id: string; subject_id: string; is_class_teacher: boolean; is_active: boolean }
export type TimetableEntry = { id: string; school_id: string; academic_year_id: string; term_id: string; teaching_assignment_id: string; day_of_week: number; start_time: string; end_time: string; room?: string | null; notes?: string | null }
export type Assessment = { id: string; school_id: string; academic_year_id: string; term_id: string; class_id: string; subject_id: string; teacher_id?: string | null; title: string; assessment_type: string; description?: string | null; assessment_date: string; max_score: string; weight: string; is_published: boolean; is_locked: boolean }
export type CurriculumOffering = { id: string; school_id: string; grade_id: string; grade: string | null; subject_id: string; subject: string | null; description?: string | null; daily_credit_hours: number; weekly_credit_hours: number; is_core: boolean }
export type CurriculumCatalog = { school_id: string; grades: { id: string; name: string }[]; subjects: { id: string; name: string; description?: string | null }[] }
export type AcademicOverview = { school_id: string; current_year: AcademicYear | null; current_term: AcademicTerm | null; teaching_assignments: number; assessments: number; published_assessments: number }
export type ReportCard = { school_id: string; student_id: string; student: string | null; class_id: string | null; academic_year_id: string; term_id: string; term: string; subjects: { subject_id: string; subject: string; percentage: number | null; assessments_count: number }[]; overall_percentage: number | null }

export async function getAcademicOverview() { return (await api.get<AcademicOverview>("/api/academic/overview", { withCredentials: true })).data }
export async function getAcademicYears() { return (await api.get<AcademicYear[]>("/api/academic/years", { withCredentials: true })).data }
export async function createAcademicYear(payload: Pick<AcademicYear, "name" | "start_date" | "end_date" | "is_current">) { return (await api.post<AcademicYear>("/api/academic/years", payload, { withCredentials: true })).data }
export async function getAcademicTerms(academicYearId?: string) { return (await api.get<AcademicTerm[]>("/api/academic/terms", { params: academicYearId ? { academic_year_id: academicYearId } : undefined, withCredentials: true })).data }
export async function createAcademicTerm(payload: Omit<AcademicTerm, "id" | "school_id" | "is_closed">) { return (await api.post<AcademicTerm>("/api/academic/terms", payload, { withCredentials: true })).data }
export async function getTeachingAssignments() { return (await api.get<TeachingAssignment[]>("/api/academic/assignments", { withCredentials: true })).data }
export async function createTeachingAssignment(payload: Omit<TeachingAssignment, "id" | "school_id" | "is_active">) { return (await api.post<TeachingAssignment>("/api/academic/assignments", payload, { withCredentials: true })).data }
export async function getTimetable(termId?: string) { return (await api.get<TimetableEntry[]>("/api/academic/timetable", { params: termId ? { term_id: termId } : undefined, withCredentials: true })).data }
export async function createTimetableEntry(payload: Omit<TimetableEntry, "id" | "school_id">) { return (await api.post<TimetableEntry>("/api/academic/timetable", payload, { withCredentials: true })).data }
export async function getAssessments(termId?: string) { return (await api.get<Assessment[]>("/api/academic/assessments", { params: termId ? { term_id: termId } : undefined, withCredentials: true })).data }
export async function createAssessment(payload: Omit<Assessment, "id" | "school_id" | "is_locked">) { return (await api.post<Assessment>("/api/academic/assessments", payload, { withCredentials: true })).data }
export async function publishAssessment(id: string, lock = false) { return (await api.post<Assessment>(`/api/academic/assessments/${id}/publish`, {}, { params: { lock }, withCredentials: true })).data }
export async function upsertAssessmentResult(assessmentId: string, payload: { student_id: string; score?: number | null; is_absent?: boolean; is_excused?: boolean; remarks?: string | null }) { return (await api.put(`/api/academic/assessments/${assessmentId}/results`, payload, { withCredentials: true })).data }
export async function getCurriculum() { return (await api.get<CurriculumOffering[]>("/api/academic/curriculum", { withCredentials: true })).data }
export async function getCurriculumCatalog() { return (await api.get<CurriculumCatalog>("/api/academic/curriculum/catalog", { withCredentials: true })).data }
export async function addCurriculumOffering(payload: { grade_id: string; subject_id: string; daily_credit_hours: number; weekly_credit_hours: number; is_core: boolean }) { return (await api.post<CurriculumOffering>("/api/academic/curriculum", payload, { withCredentials: true })).data }
export async function removeCurriculumOffering(id: string) { await api.delete(`/api/academic/curriculum/${id}`, { withCredentials: true }) }
export async function getReportCard(studentId: string, termId: string) { return (await api.get<ReportCard>(`/api/academic/report-cards/${studentId}`, { params: { term_id: termId }, withCredentials: true })).data }
