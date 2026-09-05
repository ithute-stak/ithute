import { createSlice } from "@reduxjs/toolkit"
import { SchoolResponse } from "@/types/school"

import {
    getSchoolsThunk,
    getSchoolThunk,
    createSchoolThunk,
    updateSchoolThunk,
    deleteSchoolThunk
} from "@/store/features/thunks/schoolThunks"


interface SchoolState {
    schools: SchoolResponse[]
    school: SchoolResponse | null
    loading: boolean
    error: string | null
}

const initialState: SchoolState = {
    schools: [],
    school: null,
    loading: false,
    error: null,
}

const schoolSlice = createSlice({
    name: "schools",
    initialState,
    reducers: {},
    extraReducers: (builder) => {
        builder

            // GET ALL
            .addCase(getSchoolsThunk.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(getSchoolsThunk.fulfilled, (state, action) => {
                state.loading = false;
                state.schools = action.payload;
            })
            .addCase(getSchoolsThunk.rejected, (state, action) => {
                state.loading = false;
                state.error = action.error.message || "Failed to load schools";
            })

            // GET ONE
            .addCase(getSchoolThunk.fulfilled, (state, action) => {
                state.school = action.payload;
            })

            // CREATE
            .addCase(createSchoolThunk.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(createSchoolThunk.fulfilled, (state, action) => {
                state.loading = false;
                state.schools.push(action.payload);
            })
            .addCase(createSchoolThunk.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload || "Failed to create school";
            })

            // UPDATE
            .addCase(updateSchoolThunk.fulfilled, (state, action) => {
                state.schools = state.schools.map((s) =>
                    s.id === action.payload.id ? action.payload : s
                );
            })

            // DELETE
            .addCase(deleteSchoolThunk.fulfilled, (state, action) => {
                state.schools = state.schools.filter(
                    (s) => s.id !== action.payload
                );
            });
    },
});

export default schoolSlice.reducer