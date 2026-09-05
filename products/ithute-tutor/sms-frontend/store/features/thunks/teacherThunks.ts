import { createAsyncThunk } from "@reduxjs/toolkit"
import {
    createTeacher,
    getTeachers,
    getTeacher,
    deleteTeacher,
} from "@/api/person/teacher/actions"

import { TeacherCreate, TeacherRead } from "@/types/teacher"
import {AxiosError} from "axios";
import {ApiError} from "@/store/features/thunks/schoolThunks";

/* =========================
   CREATE
========================= */
export const createTeacherThunk = createAsyncThunk<
    TeacherRead,
    TeacherCreate
>(
    "teacher/create",
    async (payload, { rejectWithValue }) => {
        try {
            return await createTeacher(payload)
        }  catch (err) {
            const error = err as AxiosError<ApiError>;

            return rejectWithValue(
                error.response?.data?.detail || "Failed to create school"
            );
        }
    }
)

/* =========================
   GET ALL
========================= */
export const fetchTeachersThunk = createAsyncThunk<
    TeacherRead[]
>(
    "teacher/fetchAll",
    async (_, { rejectWithValue }) => {
        try {
            return await getTeachers()
        }  catch (err) {
            const error = err as AxiosError<ApiError>;

            return rejectWithValue(
                error.response?.data?.detail || "Failed to create school"
            );
        }
    }
)

/* =========================
   GET ONE
========================= */
export const fetchTeacherThunk = createAsyncThunk<
    TeacherRead,
    string
>(
    "teacher/fetchOne",
    async (id, { rejectWithValue }) => {
        try {
            return await getTeacher(id)
        }  catch (err) {
            const error = err as AxiosError<ApiError>;

            return rejectWithValue(
                error.response?.data?.detail || "Failed to create school"
            );
        }
    }
)

/* =========================
   DELETE
========================= */
export const deleteTeacherThunk = createAsyncThunk<
    string, // return deleted id
    string
>(
    "teacher/delete",
    async (id, { rejectWithValue }) => {
        try {
            await deleteTeacher(id)
            return id
        }  catch (err) {
            const error = err as AxiosError<ApiError>;

            return rejectWithValue(
                error.response?.data?.detail || "Failed to create school"
            );
        }
    }
)