import { public_api_url } from "@/api/consts"

export const STUDENT_API = `${public_api_url}/students`

export const STUDENT_ENDPOINTS = {
    LIST: `${STUDENT_API}`,
    CREATE: `${STUDENT_API}`,
    READ: (id: string) => `${STUDENT_API}/${id}`,
    DELETE: (id: string) => `${STUDENT_API}/${id}`,
}