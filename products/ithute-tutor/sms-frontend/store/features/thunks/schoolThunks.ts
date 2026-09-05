import { createAsyncThunk } from "@reduxjs/toolkit"
import * as schoolAPI from "@/api/school/actions"
import {
    SchoolCreate, SchoolResponse,
    SchoolUpdate
} from "@/types/school"
import {AxiosError} from "axios";

export type ApiError = {
    detail: string
}
/* =========================
GET ALL
========================= */

export const getSchoolsThunk = createAsyncThunk(
    "schools/getAll",
    async () => {
        return await schoolAPI.getSchools()
    }
)


/* =========================
GET ONE
========================= */

export const getSchoolThunk = createAsyncThunk(
    "schools/getOne",
    async (id: string) => {
        return await schoolAPI.getSchool(id)
    }
)


/* =========================
CREATE
========================= */
export const createSchoolThunk = createAsyncThunk<
    SchoolResponse,
    SchoolCreate,
    { rejectValue: string }
>(
    "schools/create",
    async (payload, { rejectWithValue }) => {
        try {
            return await schoolAPI.createSchool(payload);
        } catch (err) {
            const error = err as AxiosError<ApiError>;

            return rejectWithValue(
                error.response?.data?.detail || "Failed to create school"
            );
        }
    }
);


/* =========================
UPDATE 59339080 rethabile
========================= */

export const updateSchoolThunk = createAsyncThunk(
    "schools/update",
    async ({
               id,
               payload,
           }: {
        id: string
        payload: SchoolUpdate
    }) => {
        return await schoolAPI.updateSchool(id, payload)
    }
)


/* =========================
DELETE
========================= */

export const deleteSchoolThunk = createAsyncThunk(
    "schools/delete",
    async (id: string) => {
        await schoolAPI.deleteSchool(id)
        return id
    }
)