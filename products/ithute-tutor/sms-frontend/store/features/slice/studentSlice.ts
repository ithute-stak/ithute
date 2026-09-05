import { createSlice } from "@reduxjs/toolkit"
import {
    createStudentThunk,
    fetchStudentsThunk,
    fetchStudentThunk,
    deleteStudentThunk,
} from "../thunks/studentThunks"

import { StudentRead } from "@/types/student"

interface StudentState {
    students: StudentRead[]
    selectedStudent: StudentRead | null
    loading: boolean
    error: string | null
}

const initialState: StudentState = {
    students: [],
    selectedStudent: null,
    loading: false,
    error: null,
}

const studentSlice = createSlice({
    name: "students",
    initialState,
    reducers: {},
    extraReducers: (builder) => {
        builder

            /* ================= CREATE ================= */
            .addCase(createStudentThunk.pending, (state) => {
                state.loading = true
            })
            .addCase(createStudentThunk.fulfilled, (state, action) => {
                state.loading = false
                state.students.unshift(action.payload)
            })
            .addCase(createStudentThunk.rejected, (state, action) => {
                state.loading = false
                state.error = action.payload as string
            })

            /* ================= FETCH ALL ================= */
            .addCase(fetchStudentsThunk.pending, (state) => {
                state.loading = true
            })
            .addCase(fetchStudentsThunk.fulfilled, (state, action) => {
                state.loading = false
                state.students = action.payload
            })
            .addCase(fetchStudentsThunk.rejected, (state, action) => {
                state.loading = false
                state.error = action.payload as string
            })

            /* ================= FETCH ONE ================= */
            .addCase(fetchStudentThunk.fulfilled, (state, action) => {
                state.selectedStudent = action.payload
            })

            /* ================= DELETE ================= */
            .addCase(deleteStudentThunk.fulfilled, (state, action) => {
                state.students = state.students.filter(
                    (s) => s.id !== action.payload
                )
            })
    },
})

export default studentSlice.reducer