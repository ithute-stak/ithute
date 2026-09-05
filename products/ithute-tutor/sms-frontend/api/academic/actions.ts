// api/academic/actions.ts

import api from "@/lib/axios-setup"

import {
    GradeCreate,
    GradeResponse,
    GradeDetailResponse,
    GradeUpdate
} from "@/types/grade"

import {
    ClassCreate,
    ClassResponse,
    ClassDetailResponse,
    ClassUpdate
} from "@/types/classes"

import {
    GRADE_ENDPOINTS,
    CLASS_ENDPOINTS
} from "@/api/academic/endpoint"


/* ========================================
   GRADE API
======================================== */

export const createGrade = async (
    payload: GradeCreate
): Promise<GradeResponse> => {
    const res = await api.post<GradeResponse>(
        GRADE_ENDPOINTS.CREATE,
        payload
    )

    return res.data
}

export const getGrades = async (): Promise<GradeResponse[]> => {
    const res = await api.get<GradeResponse[]>(
        GRADE_ENDPOINTS.LIST
    )

    return res.data
}

export const getGrade = async (
    id: string
): Promise<GradeDetailResponse> => {
    const res = await api.get<GradeDetailResponse>(
        GRADE_ENDPOINTS.READ(id)
    )

    return res.data
}

export const updateGrade = async (
    id: string,
    payload: GradeUpdate
): Promise<GradeResponse> => {
    const res = await api.put<GradeResponse>(
        GRADE_ENDPOINTS.UPDATE(id),
        payload
    )

    return res.data
}

export const deleteGrade = async (
    id: string
) => {
    const res = await api.delete(
        GRADE_ENDPOINTS.DELETE(id)
    )

    return res.data
}


/* ========================================
   CLASS API
======================================== */

export const createClass = async (
    payload: ClassCreate
): Promise<ClassResponse> => {
    const res = await api.post<ClassResponse>(
        CLASS_ENDPOINTS.CREATE,
        payload
    )

    return res.data
}

export const getClasses = async (): Promise<ClassResponse[]> => {
    const res = await api.get<ClassResponse[]>(
        CLASS_ENDPOINTS.LIST
    )

    return res.data
}

export const getClass = async (
    id: string
): Promise<ClassDetailResponse> => {
    const res = await api.get<ClassDetailResponse>(
        CLASS_ENDPOINTS.READ(id)
    )

    return res.data
}

export const updateClass = async (
    id: string,
    payload: ClassUpdate
): Promise<ClassResponse> => {
    const res = await api.put<ClassResponse>(
        CLASS_ENDPOINTS.UPDATE(id),
        payload
    )

    return res.data
}

export const deleteClass = async (
    id: string
) => {
    const res = await api.delete(
        CLASS_ENDPOINTS.DELETE(id)
    )

    return res.data
}