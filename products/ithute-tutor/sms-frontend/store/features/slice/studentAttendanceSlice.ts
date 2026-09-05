import { createSlice } from "@reduxjs/toolkit";
import {StudentAttendanceRead} from "@/types/student_attendance";
import {
    createAttendanceThunk, deleteAttendanceThunk,
    fetchSingleAttendanceThunk,
    fetchStudentAttendanceThunk, updateAttendanceThunk
} from "@/store/features/thunks/studentAttendanceThunk";



/* ========================================
   STATE
======================================== */
interface AttendanceState {
    list: StudentAttendanceRead[];

    selected?: StudentAttendanceRead | null;

    loading: boolean;

    error?: string | null;
}

const initialState: AttendanceState = {
    list: [],
    selected: null,
    loading: false,
    error: null,
};



/* ========================================
   SLICE
======================================== */
const studentAttendanceSlice = createSlice({
    name: "studentAttendance",
    initialState,
    reducers: {
        clearSelected(state) {
            state.selected = null;
        },
    },

    extraReducers: (builder) => {
        builder

            /* =========================
               FETCH ALL
            ========================= */
            .addCase(fetchStudentAttendanceThunk.pending, (state) => {
                state.loading = true;
            })
            .addCase(fetchStudentAttendanceThunk.fulfilled, (state, action) => {
                state.loading = false;
                state.list = action.payload;
            })
            .addCase(fetchStudentAttendanceThunk.rejected, (state, action) => {
                state.loading = false;
                state.error = action.error.message || "Failed to fetch attendance";
            })



            /* =========================
               FETCH ONE
            ========================= */
            .addCase(fetchSingleAttendanceThunk.fulfilled, (state, action) => {
                state.selected = action.payload;
            })



            /* =========================
               CREATE
            ========================= */
            .addCase(createAttendanceThunk.fulfilled, (state, action) => {
                state.list.unshift(action.payload);
            })



            /* =========================
               UPDATE
            ========================= */
            .addCase(updateAttendanceThunk.fulfilled, (state, action) => {
                const index = state.list.findIndex(
                    (item) => item.id === action.payload.id
                );

                if (index !== -1) {
                    state.list[index] = action.payload;
                }
            })



            /* =========================
               DELETE
            ========================= */
            .addCase(deleteAttendanceThunk.fulfilled, (state, action) => {
                state.list = state.list.filter(
                    (item) => item.id !== action.payload
                );
            });
    },
});



export const {
    clearSelected,
} = studentAttendanceSlice.actions;

export default studentAttendanceSlice.reducer;