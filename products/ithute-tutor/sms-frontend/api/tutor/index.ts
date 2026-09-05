import api from "@/lib/axios-setup"

export type AssignmentSummary = {
  id: string
  title: string
  due_at?: string | null
  status?: string
  max_score?: number | string
}

export type MasterySummary = {
  id: string
  subject_id: string
  topic_key: string
  mastery_score: number | string
  evidence_count?: number
  last_evidence?: string | null
}

export type StudyPlan = {
  id: string
  student_id: string
  title: string
  reason?: string | null
  items: Array<Record<string, unknown>>
  status: string
}

export type StudentPortalSnapshot = {
  portal: "student"
  student_id: string
  enrollment?: Record<string, unknown> | null
  assignments: AssignmentSummary[]
  submissions: Array<Record<string, unknown>>
  results: Array<Record<string, unknown>>
  mastery: MasterySummary[]
  study_plans: StudyPlan[]
}

export type ParentPortalSnapshot = {
  portal: "parent"
  children: Array<StudentPortalSnapshot & { student_id: string }>
}

export type TeacherPortalSnapshot = {
  portal: "teacher"
  teaching_assignments: Array<Record<string, unknown>>
  pending_marking: Array<Record<string, unknown>>
}

export type ManagementPortalSnapshot = {
  portal: "management"
  role: string
  school_id: string
  active_students: number
  pending_submissions: number
}

export type PortalSnapshot = StudentPortalSnapshot | ParentPortalSnapshot | TeacherPortalSnapshot | ManagementPortalSnapshot

export type TutorProfile = {
  student_id: string
  current_school_id: string
  current_class_id?: string | null
  mastery: MasterySummary[]
  weak_topics: MasterySummary[]
  assignments: AssignmentSummary[]
  recommended_modes: Array<{ mode: string; reason: string }>
}

export type PracticeQuestion = {
  id: string
  subject_id: string
  topic_key?: string | null
  prompt: string
  question_type: string
  choices?: string[] | null
  points: number | string
}

export async function getMyPortal() {
  return (await api.get<PortalSnapshot>("/api/portal/me", { withCredentials: true })).data
}

export async function getMyTutor() {
  return (await api.get<TutorProfile>("/api/tutor/me", { withCredentials: true })).data
}

export async function getLearnerTutor(studentId: string) {
  return (await api.get<TutorProfile>(`/api/tutor/students/${studentId}`, { withCredentials: true })).data
}

export async function generateStudyPlan(studentId: string) {
  return (await api.post<StudyPlan>(`/api/tutor/students/${studentId}/study-plan/auto`, {}, { withCredentials: true })).data
}

export async function getPracticeQuestions(studentId: string, limit = 10) {
  return (await api.get<PracticeQuestion[]>(`/api/tutor/students/${studentId}/practice`, { params: { limit }, withCredentials: true })).data
}
