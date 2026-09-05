import { createAsyncThunk } from "@reduxjs/toolkit"

import {
    StudentCreate,
    StudentRead,
} from "@/types/student"
import {createStudent, deleteStudent, getStudent, getStudents} from "@/api/person/student/action";

/* ========================================
   CREATE STUDENT
======================================== */
export const createStudentThunk = createAsyncThunk<
    StudentRead,
    StudentCreate
>(
    "students/create",
    async (payload, { rejectWithValue }) => {
        try {
            return await createStudent(payload)
        } catch (err: any) {
            return rejectWithValue(err.response?.data || "Error creating student")
        }
    }
)

/* ========================================
   GET ALL STUDENTS
======================================== */
export const fetchStudentsThunk = createAsyncThunk<
    StudentRead[]
>(
    "students/fetchAll",
    async (_, { rejectWithValue }) => {
        try {
            return await getStudents()
        } catch (err: any) {
            return rejectWithValue(err.response?.data || "Error fetching students")
        }
    }
)

/* ========================================
   GET SINGLE STUDENT
======================================== */
export const fetchStudentThunk = createAsyncThunk<
    StudentRead,
    string
>(
    "students/fetchOne",
    async (id, { rejectWithValue }) => {
        try {
            return await getStudent(id)
        } catch (err: any) {
            return rejectWithValue(err.response?.data || "Error fetching student")
        }
    }
)

/* ========================================
   DELETE STUDENT
======================================== */
export const deleteStudentThunk = createAsyncThunk<
    string,
    string
>(
    "students/delete",
    async (id, { rejectWithValue }) => {
        try {
            await deleteStudent(id)
            return id
        } catch (err: any) {
            return rejectWithValue(err.response?.data || "Error deleting student")
        }
    }
)