import { public_api_url } from "@/api/consts"

export const SCHOOL_API = `${public_api_url}/schools`

export const SCHOOL_ENDPOINTS = {
    LIST: `${SCHOOL_API}`,
    CREATE: `${SCHOOL_API}`,
    READ: (id: string) => `${SCHOOL_API}/${id}`,
    UPDATE: (id: string) => `${SCHOOL_API}/${id}`,
    DELETE: (id: string) => `${SCHOOL_API}/${id}`,
}