import { createSlice, PayloadAction } from "@reduxjs/toolkit"
import { TeacherRead } from "@/types/teacher"
import {
    createTeacherThunk,
    deleteTeacherThunk,
    fetchTeachersThunk,
    fetchTeacherThunk
} from "@/store/features/thunks/teacherThunks";

interface TeacherState {
    teachers: TeacherRead[]
    selectedTeacher: TeacherRead | null
    loading: boolean
    error: string | null
}

const initialState: TeacherState = {
    teachers: [],
    selectedTeacher: null,
    loading: false,
    error: null,
}

const teacherSlice = createSlice({
    name: "teacher",
    initialState,
    reducers: {
        clearSelectedTeacher: (state) => {
            state.selectedTeacher = null
        },
    },
    extraReducers: (builder) => {
        /* =========================
           FETCH ALL
        ========================= */
        builder
            .addCase(fetchTeachersThunk.pending, (state) => {
                state.loading = true
                state.error = null
            })
            .addCase(
                fetchTeachersThunk.fulfilled,
                (state, action: PayloadAction<TeacherRead[]>) => {
                    state.loading = false
                    state.teachers = action.payload
                }
            )
            .addCase(fetchTeachersThunk.rejected, (state, action) => {
                state.loading = false
                state.error = action.payload as string
            })

        /* =========================
           FETCH ONE
        ========================= */
        builder
            .addCase(fetchTeacherThunk.pending, (state) => {
                state.loading = true
            })
            .addCase(
                fetchTeacherThunk.fulfilled,
                (state, action: PayloadAction<TeacherRead>) => {
                    state.loading = false
                    state.selectedTeacher = action.payload
                }
            )
            .addCase(fetchTeacherThunk.rejected, (state, action) => {
                state.loading = false
                state.error = action.payload as string
            })

        /* =========================
           CREATE
        ========================= */
        builder
            .addCase(createTeacherThunk.pending, (state) => {
                state.loading = true
            })
            .addCase(
                createTeacherThunk.fulfilled,
                (state, action: PayloadAction<TeacherRead>) => {
                    state.loading = false
                    state.teachers.push(action.payload)
                }
            )
            .addCase(createTeacherThunk.rejected, (state, action) => {
                state.loading = false
                state.error = action.payload as string
            })

        /* =========================
           DELETE
        ========================= */
        builder
            .addCase(deleteTeacherThunk.pending, (state) => {
                state.loading = true
            })
            .addCase(
                deleteTeacherThunk.fulfilled,
                (state, action: PayloadAction<string>) => {
                    state.loading = false
                    state.teachers = state.teachers.filter(
                        (t) => t.id !== action.payload
                    )
                }
            )
            .addCase(deleteTeacherThunk.rejected, (state, action) => {
                state.loading = false
                state.error = action.payload as string
            })
    },
})

export const { clearSelectedTeacher } = teacherSlice.actions

export default teacherSlice.reducer