import api from "@/lib/axios-setup"

export type StudentDocument = {
  id: string
  school_id: string
  student_id: string
  document_type: string
  title: string
  storage_url: string
  status: "pending" | "verified" | "rejected"
  verified_by?: string | null
  verified_at?: string | null
  created_at?: string | null
}

export type DisciplineIncident = {
  id: string
  school_id: string
  student_id: string
  category: string
  severity: string
  title: string
  description: string
  occurred_on: string
  action_taken?: string | null
  status: string
  created_at?: string | null
}

export type HealthRecord = {
  id: string
  school_id: string
  student_id: string
  allergies?: string | null
  conditions?: string | null
  medications?: string | null
  emergency_notes?: string | null
  emergency_contact?: string | null
}

export async function getStudentDocuments(studentId: string) {
  return (await api.get<StudentDocument[]>(`/api/admissions/students/${studentId}/documents`, { withCredentials: true })).data
}

export async function addStudentDocument(studentId: string, payload: { document_type: string; title: string; storage_url: string }) {
  return (await api.post<StudentDocument>(`/api/admissions/students/${studentId}/documents`, payload, { withCredentials: true })).data
}

export async function reviewStudentDocument(documentId: string, status: StudentDocument["status"]) {
  return (await api.put<StudentDocument>(`/api/admissions/documents/${documentId}/review`, { status }, { withCredentials: true })).data
}

export async function getDisciplineHistory(studentId: string) {
  return (await api.get<DisciplineIncident[]>(`/api/student-support/students/${studentId}/discipline`, { withCredentials: true })).data
}

export async function createDisciplineIncident(payload: {
  student_id: string
  category: string
  severity: string
  title: string
  description: string
  occurred_on: string
  action_taken?: string | null
}) {
  return (await api.post<DisciplineIncident>("/api/student-support/discipline", payload, { withCredentials: true })).data
}

export async function getHealthRecord(studentId: string) {
  return (await api.get<HealthRecord | null>(`/api/student-support/students/${studentId}/health`, { withCredentials: true })).data
}

export async function updateHealthRecord(studentId: string, payload: Omit<HealthRecord, "id" | "school_id" | "student_id">) {
  return (await api.put<HealthRecord>(`/api/student-support/students/${studentId}/health`, payload, { withCredentials: true })).data
}
