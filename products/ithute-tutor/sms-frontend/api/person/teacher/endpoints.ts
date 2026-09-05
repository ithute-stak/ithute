import { public_api_url } from "@/api/consts"

export const PEOPLE_API = `${public_api_url}`

export const TEACHER_API = `${PEOPLE_API}/teachers`

export const TEACHER_ENDPOINTS = {
    LIST: `${TEACHER_API}`,
    CREATE: `${TEACHER_API}`,
    READ: (id: string) => `${TEACHER_API}/${id}`,
    UPDATE: (id: string) => `${TEACHER_API}/${id}`,
    DELETE: (id: string) => `${TEACHER_API}/${id}`,
}