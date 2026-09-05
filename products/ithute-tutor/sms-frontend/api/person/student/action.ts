import api from "@/lib/axios-setup"

import {
    StudentCreate,
    StudentRead,
} from "@/types/student"
import {STUDENT_ENDPOINTS} from "@/api/person/student/endpoint";

/* ========================================
   CREATE STUDENT
======================================== */
export const createStudent = async (
    payload: StudentCreate
): Promise<StudentRead> => {
    const res = await api.post<StudentRead>(
        STUDENT_ENDPOINTS.CREATE,
        payload
    )

    return res.data
}

/* ========================================
   GET ALL STUDENTS
======================================== */
export const getStudents = async (): Promise<StudentRead[]> => {
    const res = await api.get<StudentRead[]>(
        STUDENT_ENDPOINTS.LIST
    )

    return res.data
}

/* ========================================
   GET SINGLE STUDENT
======================================== */
export const getStudent = async (
    id: string
): Promise<StudentRead> => {
    const res = await api.get<StudentRead>(
        STUDENT_ENDPOINTS.READ(id)
    )

    return res.data
}

/* ========================================
   DELETE STUDENT
======================================== */
export const deleteStudent = async (
    id: string
): Promise<void> => {
    await api.delete(STUDENT_ENDPOINTS.DELETE(id))
}