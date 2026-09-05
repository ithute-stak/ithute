// store/features/finance/schoolFeeConfiguration/schoolFeeConfigurationSlice.ts

import {
    createSlice,
    PayloadAction
} from "@reduxjs/toolkit"


import {
    SchoolFeeConfigurationRead
} from "@/types/finance/schoolFeeConfiguration"
import {
    createSchoolFeeConfigurationThunk, deleteSchoolFeeConfigurationThunk,
    fetchSchoolFeeConfiguration,
    fetchSchoolFeeConfigurations, updateSchoolFeeConfigurationThunk
} from "@/store/features/thunks/finance/schoolFeeConfiguration/schoolFeeConfigurationThunk";


interface SchoolFeeConfigurationState {

    configurations: SchoolFeeConfigurationRead[]

    configuration: SchoolFeeConfigurationRead | null

    loading: boolean

    error: string | null
}


const initialState: SchoolFeeConfigurationState = {

    configurations: [],

    configuration: null,

    loading: false,

    error: null,
}


const schoolFeeConfigurationSlice = createSlice({
    name: "schoolFeeConfiguration",

    initialState,

    reducers: {

        clearSchoolFeeConfigurationState: (
            state
        ) => {

            state.error = null

            state.loading = false
        },
    },

    extraReducers: (builder) => {

        /* =========================================
           FETCH ALL
        ========================================= */

        builder.addCase(
            fetchSchoolFeeConfigurations.pending,
            (state) => {

                state.loading = true

                state.error = null
            }
        )

        builder.addCase(
            fetchSchoolFeeConfigurations.fulfilled,
            (
                state,
                action: PayloadAction<
                    SchoolFeeConfigurationRead[]
                >
            ) => {

                state.loading = false

                state.configurations =
                    action.payload
            }
        )

        builder.addCase(
            fetchSchoolFeeConfigurations.rejected,
            (state, action) => {

                state.loading = false

                state.error =
                    action.payload as string
            }
        )


        /* =========================================
           FETCH ONE
        ========================================= */

        builder.addCase(
            fetchSchoolFeeConfiguration.pending,
            (state) => {

                state.loading = true

                state.error = null
            }
        )

        builder.addCase(
            fetchSchoolFeeConfiguration.fulfilled,
            (
                state,
                action: PayloadAction<
                    SchoolFeeConfigurationRead
                >
            ) => {

                state.loading = false

                state.configuration =
                    action.payload
            }
        )

        builder.addCase(
            fetchSchoolFeeConfiguration.rejected,
            (state, action) => {

                state.loading = false

                state.error =
                    action.payload as string
            }
        )


        /* =========================================
           CREATE
        ========================================= */

        builder.addCase(
            createSchoolFeeConfigurationThunk.fulfilled,
            (
                state,
                action: PayloadAction<
                    SchoolFeeConfigurationRead
                >
            ) => {

                state.configurations.push(
                    action.payload
                )
            }
        )


        /* =========================================
           UPDATE
        ========================================= */

        builder.addCase(
            updateSchoolFeeConfigurationThunk.fulfilled,
            (
                state,
                action: PayloadAction<
                    SchoolFeeConfigurationRead
                >
            ) => {

                state.configurations =
                    state.configurations.map(
                        (item) =>
                            item.id === action.payload.id
                                ? action.payload
                                : item
                    )

                state.configuration =
                    action.payload
            }
        )


        /* =========================================
           DELETE
        ========================================= */

        builder.addCase(
            deleteSchoolFeeConfigurationThunk.fulfilled,
            (
                state,
                action: PayloadAction<string>
            ) => {

                state.configurations =
                    state.configurations.filter(
                        (item) =>
                            item.id !== action.payload
                    )
            }
        )
    },
})

export const {
    clearSchoolFeeConfigurationState
} = schoolFeeConfigurationSlice.actions

export default schoolFeeConfigurationSlice.reducer