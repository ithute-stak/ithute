// store/features/thunks/finance/feePlan/feePlanThunk.ts

import { createAsyncThunk } from "@reduxjs/toolkit"

import { AxiosError } from "axios"

import {
    createFeePlan,
    deleteFeePlan,
    getFeePlan,
    getFeePlans,
    updateFeePlan,
} from "@/api/finance/feePlan/actions"

import {
    FeePlanCreate,
    FeePlanRead,
    FeePlanUpdate,
} from "@/types/finance/feePlan"

import { ApiError } from "@/store/features/thunks/schoolThunks"

/* =========================================
   GET ALL
========================================= */

export const fetchFeePlans =
    createAsyncThunk<
        FeePlanRead[],
        void,
        { rejectValue: string }
    >(
        "feePlan/fetchAll",

        async (_, { rejectWithValue }) => {
            try {

                return await getFeePlans()

            } catch (err) {

                const error =
                    err as AxiosError<ApiError>

                return rejectWithValue(
                    error.response?.data?.detail ||
                    "Failed to fetch fee plans"
                )
            }
        }
    )

/* =========================================
   GET ONE
========================================= */

export const fetchFeePlan =
    createAsyncThunk<
        FeePlanRead,
        string,
        { rejectValue: string }
    >(
        "feePlan/fetchOne",

        async (
            id,
            { rejectWithValue }
        ) => {
            try {

                return await getFeePlan(id)

            } catch (err) {

                const error =
                    err as AxiosError<ApiError>

                return rejectWithValue(
                    error.response?.data?.detail ||
                    "Failed to fetch fee plan"
                )
            }
        }
    )

/* =========================================
   CREATE
========================================= */

export const createFeePlanThunk =
    createAsyncThunk<
        FeePlanRead,
        FeePlanCreate,
        { rejectValue: string }
    >(
        "feePlan/create",

        async (
            payload,
            { rejectWithValue }
        ) => {
            try {

                return await createFeePlan(
                    payload
                )

            } catch (err) {

                const error =
                    err as AxiosError<ApiError>

                return rejectWithValue(
                    error.response?.data?.detail ||
                    "Failed to create fee plan"
                )
            }
        }
    )

/* =========================================
   UPDATE
========================================= */

export const updateFeePlanThunk =
    createAsyncThunk<
        FeePlanRead,
        {
            id: string
            payload: FeePlanUpdate
        },
        { rejectValue: string }
    >(
        "feePlan/update",

        async (
            { id, payload },
            { rejectWithValue }
        ) => {
            try {

                return await updateFeePlan(
                    id,
                    payload
                )

            } catch (err) {

                const error =
                    err as AxiosError<ApiError>

                return rejectWithValue(
                    error.response?.data?.detail ||
                    "Failed to update fee plan"
                )
            }
        }
    )

/* =========================================
   DELETE
========================================= */

export const deleteFeePlanThunk =
    createAsyncThunk<
        string,
        string,
        { rejectValue: string }
    >(
        "feePlan/delete",

        async (
            id,
            { rejectWithValue }
        ) => {
            try {

                await deleteFeePlan(id)

                return id

            } catch (err) {

                const error =
                    err as AxiosError<ApiError>

                return rejectWithValue(
                    error.response?.data?.detail ||
                    "Failed to delete fee plan"
                )
            }
        }
    )