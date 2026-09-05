import api from "@/lib/axios-setup"

export type Lesson = {
  id: string
  class_id: string
  subject_id: string
  teacher_id?: string | null
  title: string
  summary?: string | null
  body?: string | null
  resource_url?: string | null
  sequence: number
  status: "draft" | "published" | "archived"
  published_at?: string | null
}

export type Assignment = {
  id: string
  class_id: string
  subject_id: string
  teacher_id?: string | null
  title: string
  instructions: string
  due_at?: string | null
  max_score: number | string
  status: "draft" | "published" | "closed" | "archived"
  allow_resubmission: boolean
  published_at?: string | null
}

export type Submission = {
  id: string
  assignment_id: string
  student_id: string
  attempt_no: number
  answer_text?: string | null
  attachment_url?: string | null
  status: string
  submitted_at?: string | null
  score?: number | string | null
  feedback?: string | null
}

export async function getLessons() { return (await api.get<Lesson[]>("/api/lms/lessons", { withCredentials: true })).data }
export async function createLesson(payload: { class_id: string; subject_id: string; title: string; summary?: string; body?: string; resource_url?: string; sequence?: number }) { return (await api.post<Lesson>("/api/lms/lessons", payload, { withCredentials: true })).data }
export async function publishLesson(id: string) { return (await api.put<Lesson>(`/api/lms/lessons/${id}/publish`, {}, { withCredentials: true })).data }
export async function getAssignments() { return (await api.get<Assignment[]>("/api/lms/assignments", { withCredentials: true })).data }
export async function createAssignment(payload: { class_id: string; subject_id: string; title: string; instructions: string; due_at?: string | null; max_score?: number; allow_resubmission?: boolean }) { return (await api.post<Assignment>("/api/lms/assignments", payload, { withCredentials: true })).data }
export async function publishAssignment(id: string) { return (await api.put<Assignment>(`/api/lms/assignments/${id}/publish`, {}, { withCredentials: true })).data }
export async function submitAssignment(id: string, payload: { answer_text?: string; attachment_url?: string }) { return (await api.post<Submission>(`/api/lms/assignments/${id}/submissions`, payload, { withCredentials: true })).data }
export async function getAssignmentSubmissions(id: string) { return (await api.get<Submission[]>(`/api/lms/assignments/${id}/submissions`, { withCredentials: true })).data }
export async function gradeSubmission(id: string, payload: { score: number; feedback?: string }) { return (await api.put<Submission>(`/api/lms/submissions/${id}/grade`, payload, { withCredentials: true })).data }
