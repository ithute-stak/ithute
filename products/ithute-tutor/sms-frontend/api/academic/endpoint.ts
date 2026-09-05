// api/academic/endpoint.ts

import { public_api_url } from "@/api/consts"

export const ACADEMIC_API = `${public_api_url}`

export const GRADE_API = `${ACADEMIC_API}/grades`
export const CLASS_API = `${ACADEMIC_API}/classes`

export const GRADE_ENDPOINTS = {
    LIST: `${GRADE_API}`,
    CREATE: `${GRADE_API}`,
    READ: (id: string) => `${GRADE_API}/${id}`,
    UPDATE: (id: string) => `${GRADE_API}/${id}`,
    DELETE: (id: string) => `${GRADE_API}/${id}`,
}

export const CLASS_ENDPOINTS = {
    LIST: `${CLASS_API}`,
    CREATE: `${CLASS_API}`,
    READ: (id: string) => `${CLASS_API}/${id}`,
    UPDATE: (id: string) => `${CLASS_API}/${id}`,
    DELETE: (id: string) => `${CLASS_API}/${id}`,
}