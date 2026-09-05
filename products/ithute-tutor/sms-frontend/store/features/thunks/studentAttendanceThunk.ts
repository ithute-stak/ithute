import { createAsyncThunk } from "@reduxjs/toolkit";
import {
    createStudentAttendance, deleteStudentAttendance,
    getStudentAttendance,
    getStudentAttendanceRecord, updateStudentAttendance
} from "@/api/person/student/attendance/actions";
import {StudentAttendanceCreate, StudentAttendanceUpdate} from "@/types/student_attendance";


/* ========================================
   GET ALL
======================================== */
export const fetchStudentAttendanceThunk = createAsyncThunk(
    "attendance/fetchAll",
    async () => {
        return await getStudentAttendance();
    }
);

/* ========================================
   GET ONE
======================================== */
export const fetchSingleAttendanceThunk = createAsyncThunk(
    "attendance/fetchOne",
    async (id: string) => {
        return await getStudentAttendanceRecord(id);
    }
);

/* ========================================
   CREATE
======================================== */
export const createAttendanceThunk = createAsyncThunk(
    "attendance/create",
    async (payload: StudentAttendanceCreate) => {
        return await createStudentAttendance(payload);
    }
);

/* ========================================
   UPDATE
======================================== */
export const updateAttendanceThunk = createAsyncThunk(
    "attendance/update",
    async ({
               id,
               payload,
           }: {
        id: string;
        payload: StudentAttendanceUpdate;
    }) => {
        return await updateStudentAttendance(id, payload);
    }
);

/* ========================================
   DELETE
======================================== */
export const deleteAttendanceThunk = createAsyncThunk(
    "attendance/delete",
    async (id: string) => {
        await deleteStudentAttendance(id);
        return id;
    }
);