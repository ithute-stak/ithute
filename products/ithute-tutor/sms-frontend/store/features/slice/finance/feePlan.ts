// store/features/slices/finance/feePlanSlice.ts

import {
    createSlice,
    PayloadAction,
} from "@reduxjs/toolkit"

import {
    FeePlanRead,
} from "@/types/finance/feePlan"
import {
    createFeePlanThunk, deleteFeePlanThunk,
    fetchFeePlan,
    fetchFeePlans,
    updateFeePlanThunk
} from "@/store/features/thunks/finance/feePlan";


interface FeePlanState {
    feePlans: FeePlanRead[]

    feePlan:
        | FeePlanRead
        | null

    loading: boolean

    error:
        | string
        | null
}

const initialState: FeePlanState =
    {
        feePlans: [],

        feePlan: null,

        loading: false,

        error: null,
    }

export const feePlanSlice =
    createSlice({
        name: "feePlan",

        initialState,

        reducers: {
            clearFeePlanState: (
                state
            ) => {
                state.error = null

                state.loading = false
            },
        },

        extraReducers: (
            builder
        ) => {
            /*
            =========================================
            FETCH ALL
            =========================================
            */
            builder
                .addCase(
                    fetchFeePlans.pending,
                    (state) => {
                        state.loading = true

                        state.error =
                            null
                    }
                )

                .addCase(
                    fetchFeePlans.fulfilled,
                    (
                        state,
                        action: PayloadAction<
                            FeePlanRead[]
                        >
                    ) => {
                        state.loading = false

                        state.feePlans =
                            action.payload
                    }
                )

                .addCase(
                    fetchFeePlans.rejected,
                    (
                        state,
                        action
                    ) => {
                        state.loading = false

                        state.error =
                            action.payload as string
                    }
                )

            /*
            =========================================
            FETCH ONE
            =========================================
            */
            builder
                .addCase(
                    fetchFeePlan.pending,
                    (state) => {
                        state.loading = true

                        state.error =
                            null
                    }
                )

                .addCase(
                    fetchFeePlan.fulfilled,
                    (
                        state,
                        action: PayloadAction<FeePlanRead>
                    ) => {
                        state.loading = false

                        state.feePlan =
                            action.payload
                    }
                )

                .addCase(
                    fetchFeePlan.rejected,
                    (
                        state,
                        action
                    ) => {
                        state.loading = false

                        state.error =
                            action.payload as string
                    }
                )

            /*
            =========================================
            CREATE
            =========================================
            */
            builder
                .addCase(
                    createFeePlanThunk.pending,
                    (state) => {
                        state.loading = true

                        state.error =
                            null
                    }
                )

                .addCase(
                    createFeePlanThunk.fulfilled,
                    (
                        state,
                        action: PayloadAction<FeePlanRead>
                    ) => {
                        state.loading = false

                        state.feePlans.unshift(
                            action.payload
                        )
                    }
                )

                .addCase(
                    createFeePlanThunk.rejected,
                    (
                        state,
                        action
                    ) => {
                        state.loading = false

                        state.error =
                            action.payload as string
                    }
                )

            /*
            =========================================
            UPDATE
            =========================================
            */
            builder
                .addCase(
                    updateFeePlanThunk.pending,
                    (state) => {
                        state.loading = true

                        state.error =
                            null
                    }
                )

                .addCase(
                    updateFeePlanThunk.fulfilled,
                    (
                        state,
                        action: PayloadAction<FeePlanRead>
                    ) => {
                        state.loading = false

                        state.feePlans =
                            state.feePlans.map(
                                (
                                    plan
                                ) =>
                                    plan.id ===
                                    action
                                        .payload
                                        .id
                                        ? action.payload
                                        : plan
                            )
                    }
                )

                .addCase(
                    updateFeePlanThunk.rejected,
                    (
                        state,
                        action
                    ) => {
                        state.loading = false

                        state.error =
                            action.payload as string
                    }
                )

            /*
            =========================================
            DELETE
            =========================================
            */
            builder
                .addCase(
                    deleteFeePlanThunk.pending,
                    (state) => {
                        state.loading = true

                        state.error =
                            null
                    }
                )

                .addCase(
                    deleteFeePlanThunk.fulfilled,
                    (
                        state,
                        action: PayloadAction<string>
                    ) => {
                        state.loading = false

                        state.feePlans =
                            state.feePlans.filter(
                                (
                                    plan
                                ) =>
                                    plan.id !==
                                    action.payload
                            )
                    }
                )

                .addCase(
                    deleteFeePlanThunk.rejected,
                    (
                        state,
                        action
                    ) => {
                        state.loading = false

                        state.error =
                            action.payload as string
                    }
                )
        },
    })

export const {
    clearFeePlanState,
} = feePlanSlice.actions

export default feePlanSlice.reducer