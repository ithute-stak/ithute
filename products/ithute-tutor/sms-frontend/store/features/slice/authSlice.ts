import { createSlice, PayloadAction } from "@reduxjs/toolkit";

import { getCurrentUserThunk, logoutThunk, type AuthFailure } from "@/store/features/thunks/authThunks";
import { UserAuthResponse } from "@/types/user";

export type AuthStatus = "idle" | "checking" | "authenticated" | "anonymous" | "unavailable";

interface AuthState {
    user: UserAuthResponse | null;
    // Access tokens may be held in memory after a refresh, but the central
    // refresh token remains HttpOnly and is never stored in Redux/localStorage.
    token: string | null;
    status: AuthStatus;
    loading: boolean;
    error: string | null;
}

const initialState: AuthState = {
    user: null,
    token: null,
    status: "idle",
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
            state.status = "anonymous";
            state.loading = false;
            state.error = null;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(getCurrentUserThunk.pending, (state) => {
                state.status = "checking";
                state.loading = true;
                state.error = null;
            })
            .addCase(getCurrentUserThunk.fulfilled, (state, action) => {
                state.user = action.payload;
                state.status = "authenticated";
                state.loading = false;
                state.error = null;
            })
            .addCase(getCurrentUserThunk.rejected, (state, action) => {
                const failure = action.payload as AuthFailure | undefined;
                state.loading = false;
                state.error = failure?.message || action.error.message || "Unable to verify Tutor session";

                if (failure?.status === 401 || failure?.status === 403) {
                    state.user = null;
                    state.token = null;
                    state.status = "anonymous";
                } else {
                    // Do not turn a central-Auth/network outage into a logout.
                    state.status = "unavailable";
                }
            })
            .addCase(logoutThunk.fulfilled, (state) => {
                state.user = null;
                state.token = null;
                state.status = "anonymous";
                state.loading = false;
                state.error = null;
            })
            .addCase(logoutThunk.rejected, (state) => {
                state.user = null;
                state.token = null;
                state.status = "anonymous";
                state.loading = false;
            });
    },
});

export const { setToken, clearAuth } = authSlice.actions;
export default authSlice.reducer;
