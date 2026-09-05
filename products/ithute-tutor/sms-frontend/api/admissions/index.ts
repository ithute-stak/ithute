import api from "@/lib/axios-setup"

export type AdmissionStatus = "draft" | "submitted" | "under_review" | "accepted" | "waitlisted" | "rejected" | "enrolled"

export type AdmissionApplication = {
  id: string
  school_id: string
  applicant_first_name: string
  applicant_last_name: string
  date_of_birth?: string | null
  guardian_name: string
  guardian_email?: string | null
  guardian_phone?: string | null
  desired_grade_id?: string | null
  desired_class_id?: string | null
  status: AdmissionStatus
  notes?: string | null
  created_at?: string | null
}

export type AdmissionInput = {
  applicant_first_name: string
  applicant_last_name: string
  date_of_birth?: string | null
  guardian_name: string
  guardian_email?: string | null
  guardian_phone?: string | null
  desired_grade_id?: string | null
  desired_class_id?: string | null
  notes?: string | null
}

export async function getAdmissionApplications(status?: string) {
  return (await api.get<AdmissionApplication[]>("/api/admissions/applications", { params: status ? { status } : undefined, withCredentials: true })).data
}

export async function createAdmissionApplication(payload: AdmissionInput) {
  return (await api.post<AdmissionApplication>("/api/admissions/applications", payload, { withCredentials: true })).data
}

export async function decideAdmissionApplication(id: string, status: Exclude<AdmissionStatus, "draft" | "submitted">, notes?: string) {
  return (await api.put<AdmissionApplication>(`/api/admissions/applications/${id}/decision`, { status, notes: notes || null }, { withCredentials: true })).data
}
