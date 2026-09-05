// store/features/slice/gradeSlice.ts

import { createSlice } from "@reduxjs/toolkit"
import {
    GradeResponse,
    GradeDetailResponse
} from "@/types/grade"

import {
    getGradesThunk,
    getGradeThunk,
    createGradeThunk,
    updateGradeThunk,
    deleteGradeThunk
} from "@/store/features/thunks/gradeThunks"

interface GradeState {
    grades: GradeResponse[]
    grade: GradeDetailResponse | null
    loading: boolean
    error: string | null
}

const initialState: GradeState = {
    grades: [],
    grade: null,
    loading: false,
    error: null,
}

const gradeSlice = createSlice({
    name: "grades",
    initialState,
    reducers: {},
    extraReducers: (builder) => {
        builder

            // GET ALL
            .addCase(getGradesThunk.pending, (state) => {
                state.loading = true
            })
            .addCase(getGradesThunk.fulfilled, (state, action) => {
                state.loading = false
                state.grades = action.payload
            })
            .addCase(getGradesThunk.rejected, (state, action) => {
                state.loading = false
                state.error = action.error.message || "Failed to fetch grades"
            })

            // GET ONE
            .addCase(getGradeThunk.fulfilled, (state, action) => {
                state.grade = action.payload
            })

            // CREATE
            .addCase(createGradeThunk.fulfilled, (state, action) => {
                state.grades.push(action.payload)
            })

            // UPDATE
            .addCase(updateGradeThunk.fulfilled, (state, action) => {
                state.grades = state.grades.map((grade) =>
                    grade.id === action.payload.id
                        ? action.payload
                        : grade
                )
            })

            // DELETE
            .addCase(deleteGradeThunk.fulfilled, (state, action) => {
                state.grades = state.grades.filter(
                    (grade) => grade.id !== action.payload
                )
            })
    },
})

export default gradeSlice.reducer