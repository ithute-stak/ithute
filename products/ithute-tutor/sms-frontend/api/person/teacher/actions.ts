import api from "@/lib/axios-setup"
import {TEACHER_ENDPOINTS} from "@/api/person/teacher/endpoints";
import {TeacherCreate, TeacherRead} from "@/types/teacher";



/* ========================================
   TEACHER API
======================================== */

export const createTeacher = async (
    payload: TeacherCreate
): Promise<TeacherRead> => {
    const res = await api.post<TeacherRead>(
        TEACHER_ENDPOINTS.CREATE,
        payload
    )

    return res.data
}

export const getTeachers = async (): Promise<TeacherRead[]> => {
    const res = await api.get<TeacherRead[]>(
        TEACHER_ENDPOINTS.LIST
    )

    return res.data
}

export const getTeacher = async (
    id: string
): Promise<TeacherRead> => {
    const res = await api.get<TeacherRead>(
        TEACHER_ENDPOINTS.READ(id)
    )

    return res.data
}

/*export const updateTeacher = async (
    id: string,
    payload: TeacherUpdate
): Promise<TeacherRead> => {
    const res = await api.put<TeacherRead>(
        TEACHER_ENDPOINTS.UPDATE(id),
        payload
    )

    return res.data
}*/

export const deleteTeacher = async (
    id: string
) => {
    const res = await api.delete(
        TEACHER_ENDPOINTS.DELETE(id)
    )

    return res.data
}