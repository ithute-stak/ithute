import { createAsyncThunk } from "@reduxjs/toolkit";
import * as authAPI from "@/api/auth/actions";

export const getCurrentUserThunk = createAsyncThunk(
    "auth/me",
    async () => authAPI.getCurrentUser(),
);

export const logoutThunk = createAsyncThunk(
    "auth/logout",
    async () => {
        await authAPI.logout();
    },
);
