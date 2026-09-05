// store/features/slice/classSlice.ts

import { createSlice } from "@reduxjs/toolkit"

import {
    ClassResponse,
    ClassDetailResponse
} from "@/types/classes"

import {
    getClassesThunk,
    getClassThunk,
    createClassThunk,
    updateClassThunk,
    deleteClassThunk
} from "@/store/features/thunks/classThunks"

interface ClassState {
    classes: ClassResponse[]
    classroom: ClassDetailResponse | null
    loading: boolean
    error: string | null
}

const initialState: ClassState = {
    classes: [],
    classroom: null,
    loading: false,
    error: null,
}

const classSlice = createSlice({
    name: "classes",
    initialState,
    reducers: {},
    extraReducers: (builder) => {
        builder

            // GET ALL
            .addCase(getClassesThunk.pending, (state) => {
                state.loading = true
            })
            .addCase(getClassesThunk.fulfilled, (state, action) => {
                state.loading = false
                state.classes = action.payload
            })
            .addCase(getClassesThunk.rejected, (state, action) => {
                state.loading = false
                state.error = action.error.message || "Failed to fetch classes"
            })

            // GET ONE
            .addCase(getClassThunk.fulfilled, (state, action) => {
                state.classroom = action.payload
            })

            // CREATE
            .addCase(createClassThunk.fulfilled, (state, action) => {
                state.classes.push(action.payload)
            })

            // UPDATE
            .addCase(updateClassThunk.fulfilled, (state, action) => {
                state.classes = state.classes.map((item) =>
                    item.id === action.payload.id
                        ? action.payload
                        : item
                )
            })

            // DELETE
            .addCase(deleteClassThunk.fulfilled, (state, action) => {
                state.classes = state.classes.filter(
                    (item) => item.id !== action.payload
                )
            })
    },
})

export default classSlice.reducer