// store/features/thunks/gradeThunks.ts

import { createAsyncThunk } from "@reduxjs/toolkit"
import * as academicAPI from "@/api/academic/actions"
import {
    GradeCreate,
    GradeUpdate
} from "@/types/grade"


/* ========================================
   GET ALL GRADES
======================================== */

export const getGradesThunk = createAsyncThunk(
    "grades/getAll",
    async () => {
        return await academicAPI.getGrades()
    }
)
/* ========================================
   GET SINGLE GRADE
======================================== */

export const getGradeThunk = createAsyncThunk(
    "grades/getOne",
    async (id: string) => {
        return await academicAPI.getGrade(id)
    }
)


/* ========================================
   CREATE GRADE
======================================== */

export const createGradeThunk = createAsyncThunk(
    "grades/create",
    async (payload: GradeCreate) => {
        return await academicAPI.createGrade(payload)
    }
)


/* ========================================
   UPDATE GRADE
======================================== */

export const updateGradeThunk = createAsyncThunk(
    "grades/update",
    async ({
               id,
               payload,
           }: {
        id: string
        payload: GradeUpdate
    }) => {
        return await academicAPI.updateGrade(id, payload)
    }
)


/* ========================================
   DELETE GRADE
======================================== */

export const deleteGradeThunk = createAsyncThunk(
    "grades/delete",
    async (id: string) => {
        await academicAPI.deleteGrade(id)
        return id
    }
)