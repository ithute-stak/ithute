import { createSlice, PayloadAction } from "@reduxjs/toolkit";

import { getCurrentUserThunk, logoutThunk } from "@/store/features/thunks/authThunks";
import { UserAuthResponse } from "@/types/user";

interface AuthState {
    user: UserAuthResponse | null;
    // Access tokens may be held in memory after a refresh, but the central
    // refresh token remains HttpOnly and is never stored in Redux/localStorage.
    token: string | null;
    loading: boolean;
    error: string | null;
}

const initialState: AuthState = {
    user: null,
    token: null,
    loading: false,
    error: null,
};

const authSlice = createSlice({
    name: "auth",
    initialState,
    reducers: {
        setToken: (state, action: PayloadAction<string>) => {
            state.token = action.payload;
        },
        clearAuth: (state) => {
            state.user = null;
            state.token = null;
            state.error = null;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(getCurrentUserThunk.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(getCurrentUserThunk.fulfilled, (state, action) => {
                state.user = action.payload;
                state.loading = false;
            })
            .addCase(getCurrentUserThunk.rejected, (state) => {
                state.user = null;
                state.loading = false;
            })
            .addCase(logoutThunk.fulfilled, (state) => {
                state.user = null;
                state.token = null;
                state.loading = false;
            });
    },
});

export const { setToken, clearAuth } = authSlice.actions;
export default authSlice.reducer;
