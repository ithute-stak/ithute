// store/features/finance/schoolFeeConfiguration/schoolFeeConfigurationThunk.ts

import { createAsyncThunk } from "@reduxjs/toolkit"

import { AxiosError } from "axios"

import {
    SchoolFeeConfigurationCreate,
    SchoolFeeConfigurationRead,
    SchoolFeeConfigurationUpdate,
} from "@/types/finance/schoolFeeConfiguration"

import {
    createSchoolFeeConfiguration,
    deleteSchoolFeeConfiguration,
    getSchoolFeeConfiguration,
    getSchoolFeeConfigurations,
    updateSchoolFeeConfiguration
} from "@/api/finance/feeConfig/actions"

import { ApiError } from "@/store/features/thunks/schoolThunks"


/* =========================================
   GET ALL
========================================= */

export const fetchSchoolFeeConfigurations =
    createAsyncThunk<
        SchoolFeeConfigurationRead[],
        void,
        { rejectValue: string }
    >(
        "schoolFeeConfiguration/fetchAll",

        async (_, { rejectWithValue }) => {
            try {

                return await getSchoolFeeConfigurations()

            } catch (err) {

                const error =
                    err as AxiosError<ApiError>

                return rejectWithValue(
                    error.response?.data?.detail ||
                    "Failed to fetch configurations"
                )
            }
        }
    )


/* =========================================
   GET ONE
========================================= */

export const fetchSchoolFeeConfiguration =
    createAsyncThunk<
        SchoolFeeConfigurationRead,
        string,
        { rejectValue: string }
    >(
        "schoolFeeConfiguration/fetchOne",

        async (id, { rejectWithValue }) => {
            try {

                return await getSchoolFeeConfiguration(id)

            } catch (err) {

                const error =
                    err as AxiosError<ApiError>

                return rejectWithValue(
                    error.response?.data?.detail ||
                    "Failed to fetch configuration"
                )
            }
        }
    )


/* =========================================
   CREATE
========================================= */

export const createSchoolFeeConfigurationThunk =
    createAsyncThunk<
        SchoolFeeConfigurationRead,
        SchoolFeeConfigurationCreate,
        { rejectValue: string }
    >(
        "schoolFeeConfiguration/create",

        async (payload, { rejectWithValue }) => {
            try {

                return await createSchoolFeeConfiguration(
                    payload
                )

            } catch (err) {

                const error =
                    err as AxiosError<ApiError>

                return rejectWithValue(
                    error.response?.data?.detail ||
                    "Failed to create configuration"
                )
            }
        }
    )


/* =========================================
   UPDATE
========================================= */

export const updateSchoolFeeConfigurationThunk =
    createAsyncThunk<
        SchoolFeeConfigurationRead,
        {
            id: string
            payload: SchoolFeeConfigurationUpdate
        },
        { rejectValue: string }
    >(
        "schoolFeeConfiguration/update",

        async (
            { id, payload },
            { rejectWithValue }
        ) => {
            try {

                return await updateSchoolFeeConfiguration(
                    id,
                    payload
                )

            } catch (err) {

                const error =
                    err as AxiosError<ApiError>

                return rejectWithValue(
                    error.response?.data?.detail ||
                    "Failed to update configuration"
                )
            }
        }
    )


/* =========================================
   DELETE
========================================= */

export const deleteSchoolFeeConfigurationThunk =
    createAsyncThunk<
        string,
        string,
        { rejectValue: string }
    >(
        "schoolFeeConfiguration/delete",

        async (id, { rejectWithValue }) => {
            try {

                await deleteSchoolFeeConfiguration(id)

                return id

            } catch (err) {

                const error =
                    err as AxiosError<ApiError>

                return rejectWithValue(
                    error.response?.data?.detail ||
                    "Failed to delete configuration"
                )
            }
        }
    )