import api from "@/lib/axios-setup"
import { SCHOOL_ENDPOINTS } from "@/api/school/endpoint"
import {
    SchoolCreate,
    SchoolResponse,
    SchoolUpdate
} from "@/types/school"


/* =========================
CREATE
========================= */

export const createSchool = async (
    payload: SchoolCreate
): Promise<SchoolResponse> => {
    const res = await api.post<SchoolResponse>(
        SCHOOL_ENDPOINTS.CREATE,
        payload
    )
    return res.data
}

/* =========================
GET ALL
========================= */

export const getSchools = async (): Promise<SchoolResponse[]> => {
    const res = await api.get<SchoolResponse[]>(
        SCHOOL_ENDPOINTS.LIST
    )
    return res.data
}

/* =========================
GET ONE
========================= */

export const getSchool = async (
    id: string
): Promise<SchoolResponse> => {
    const res = await api.get<SchoolResponse>(
        SCHOOL_ENDPOINTS.READ(id)
    )
    return res.data
}

/* =========================
UPDATE
========================= */

export const updateSchool = async (
    id: string,
    payload: SchoolUpdate
): Promise<SchoolResponse> => {
    const res = await api.put<SchoolResponse>(
        SCHOOL_ENDPOINTS.UPDATE(id),
        payload
    )
    return res.data
}

/* =========================
DELETE
========================= */

export const deleteSchool = async (
    id: string
) => {
    const res = await api.delete(
        SCHOOL_ENDPOINTS.DELETE(id)
    )
    return res.data
}