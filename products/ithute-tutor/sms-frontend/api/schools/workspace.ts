import api from "@/lib/axios-setup"
import type { SchoolMembership, SchoolProfile, SchoolWorkspace } from "@/types/school-workspace"

export type CreateSchoolWorkspacePayload = {
  name: string
  category: string
  school_code?: string | null
  registration_number?: string | null
  motto?: string | null
  address?: string | null
  phone?: string | null
  email?: string | null
  website?: string | null
}

export async function getSchoolWorkspaces(): Promise<SchoolMembership[]> {
  const response = await api.get<SchoolMembership[]>("/api/schools/mine", { withCredentials: true })
  return response.data
}

export async function getCurrentSchoolWorkspace(): Promise<SchoolWorkspace> {
  const response = await api.get<SchoolWorkspace>("/api/schools/workspace", { withCredentials: true })
  return response.data
}

export async function createSchoolWorkspace(
  payload: CreateSchoolWorkspacePayload,
): Promise<SchoolProfile> {
  const response = await api.post<SchoolProfile>("/api/schools/", payload, { withCredentials: true })
  return response.data
}

export async function activateSchoolWorkspace(schoolId: string): Promise<void> {
  await api.post(`/api/schools/${schoolId}/activate`, {}, { withCredentials: true })
}

export async function updateSchoolProfile(
  schoolId: string,
  payload: Partial<SchoolProfile>,
): Promise<SchoolProfile> {
  const response = await api.put<SchoolProfile>(`/api/schools/${schoolId}`, payload, {
    withCredentials: true,
  })
  return response.data
}
