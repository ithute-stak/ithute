import axios from "axios";
import { createAsyncThunk } from "@reduxjs/toolkit";
import * as authAPI from "@/api/auth/actions";

export type AuthFailure = {
    status: number | null;
    message: string;
};

export const getCurrentUserThunk = createAsyncThunk(
    "auth/me",
    async (_, { rejectWithValue }) => {
        try {
            return await authAPI.getCurrentUser();
        } catch (error) {
            if (axios.isAxiosError(error)) {
                const detail = error.response?.data?.detail;
                return rejectWithValue({
                    status: error.response?.status ?? null,
                    message: typeof detail === "string" ? detail : error.message,
                } satisfies AuthFailure);
            }
            return rejectWithValue({
                status: null,
                message: error instanceof Error ? error.message : "Unable to verify Tutor session",
            } satisfies AuthFailure);
        }
    },
);

export const logoutThunk = createAsyncThunk(
    "auth/logout",
    async (_, { rejectWithValue }) => {
        try {
            await authAPI.logout();
        } catch (error) {
            // The UI should still clear its in-memory auth after logout failure;
            // the backend endpoint is designed to be idempotent/local-first.
            return rejectWithValue({
                status: axios.isAxiosError(error) ? error.response?.status ?? null : null,
                message: error instanceof Error ? error.message : "Unable to complete Tutor logout",
            } satisfies AuthFailure);
        }
    },
);
