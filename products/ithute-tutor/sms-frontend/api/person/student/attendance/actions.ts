// api/student-attendance/actions.ts

import api from "@/lib/axios-setup";
import {
    AttendanceKPI,
    StudentAttendanceCreate,
    StudentAttendanceRead,
    StudentAttendanceUpdate
} from "@/types/student_attendance";
import {STUDENT_ATTENDANCE_ENDPOINTS} from "@/api/person/student/attendance/endpoint";




/* ========================================
   CREATE ATTENDANCE
======================================== */

export const createStudentAttendance =
    async (
        payload: StudentAttendanceCreate
    ): Promise<StudentAttendanceRead> => {

        const res =
            await api.post<StudentAttendanceRead>(
                STUDENT_ATTENDANCE_ENDPOINTS.CREATE,
                payload
            );

        return res.data;
    };



/* ========================================
   GET ALL ATTENDANCE
======================================== */

export const getStudentAttendance =
    async (): Promise<StudentAttendanceRead[]> => {

        const res =
            await api.get<StudentAttendanceRead[]>(
                STUDENT_ATTENDANCE_ENDPOINTS.LIST
            );

        return res.data;
    };



/* ========================================
   GET SINGLE ATTENDANCE
======================================== */

export const getStudentAttendanceRecord =
    async (
        id: string
    ): Promise<StudentAttendanceRead> => {

        const res =
            await api.get<StudentAttendanceRead>(
                STUDENT_ATTENDANCE_ENDPOINTS.READ(id)
            );

        return res.data;
    };



/* ========================================
   UPDATE ATTENDANCE
======================================== */

export const updateStudentAttendance =
    async (
        id: string,
        payload: StudentAttendanceUpdate
    ): Promise<StudentAttendanceRead> => {

        const res =
            await api.put<StudentAttendanceRead>(
                STUDENT_ATTENDANCE_ENDPOINTS.UPDATE(id),
                payload
            );

        return res.data;
    };



/* ========================================
   DELETE ATTENDANCE
======================================== */

export const deleteStudentAttendance =
    async (
        id: string
    ): Promise<void> => {

        await api.delete(
            STUDENT_ATTENDANCE_ENDPOINTS.DELETE(id)
        );
    };



/* ========================================
   ATTENDANCE KPI
======================================== */

export const getAttendanceKPI =
    async (): Promise<AttendanceKPI> => {

        const res =
            await api.get<AttendanceKPI>(
                STUDENT_ATTENDANCE_ENDPOINTS.KPI
            );

        return res.data;
    };