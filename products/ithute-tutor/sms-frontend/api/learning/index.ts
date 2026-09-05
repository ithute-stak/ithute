import api from "@/lib/axios-setup"

export type PeerApproval = {
  school_id: string
  school?: string | null
  approved_at?: string | null
  note?: string | null
}

export type LearningMaterial = {
  id: string
  school_id: string
  source_school?: string | null
  author_user_id?: string | null
  title: string
  description?: string | null
  content_type: "note" | "document" | "link" | "video" | "worksheet" | "lesson" | "other"
  body?: string | null
  resource_url?: string | null
  grade_id?: string | null
  grade?: string | null
  subject_id?: string | null
  subject?: string | null
  visibility: "school" | "public"
  moderation_status: "draft" | "pending" | "approved" | "rejected" | "archived"
  approval_source?: "platform" | "peer" | null
  peer_approval_threshold: number
  peer_approval_count: number
  peer_approvals: PeerApproval[]
  platform_moderation_note?: string | null
  published_at?: string | null
  is_active: boolean
  created_at?: string | null
  updated_at?: string | null
}

export type LearningMaterialInput = {
  title: string
  description?: string | null
  content_type: LearningMaterial["content_type"]
  body?: string | null
  resource_url?: string | null
  grade_id?: string | null
  subject_id?: string | null
  visibility: "school" | "public"
  peer_approval_threshold: number
}

export async function getSharedLearningLibrary(params?: {
  grade_id?: string
  subject_id?: string
  source_school_id?: string
  q?: string
}) {
  return (await api.get<LearningMaterial[]>("/api/learning/library", { params, withCredentials: true })).data
}

export async function getSchoolLearningMaterials() {
  return (await api.get<LearningMaterial[]>("/api/learning/materials/mine", { withCredentials: true })).data
}

export async function getPeerReviewQueue() {
  return (await api.get<LearningMaterial[]>("/api/learning/review-queue", { withCredentials: true })).data
}

export async function getPlatformReviewQueue() {
  return (await api.get<LearningMaterial[]>("/api/learning/platform-review-queue", { withCredentials: true })).data
}

export async function createLearningMaterial(payload: LearningMaterialInput) {
  return (await api.post<LearningMaterial>("/api/learning/materials", payload, { withCredentials: true })).data
}

export async function updateLearningMaterial(id: string, payload: LearningMaterialInput) {
  return (await api.put<LearningMaterial>(`/api/learning/materials/${id}`, payload, { withCredentials: true })).data
}

export async function submitLearningMaterial(id: string) {
  return (await api.post<LearningMaterial>(`/api/learning/materials/${id}/submit`, {}, { withCredentials: true })).data
}

export async function peerApproveLearningMaterial(id: string, note?: string) {
  return (await api.post<LearningMaterial>(`/api/learning/materials/${id}/peer-approve`, { note: note || null }, { withCredentials: true })).data
}

export async function platformModerateLearningMaterial(id: string, decision: "approved" | "rejected", note?: string) {
  return (await api.post<LearningMaterial>(`/api/learning/materials/${id}/platform-moderate`, { decision, note: note || null }, { withCredentials: true })).data
}

export async function archiveLearningMaterial(id: string) {
  return (await api.post(`/api/learning/materials/${id}/archive`, {}, { withCredentials: true })).data
}
