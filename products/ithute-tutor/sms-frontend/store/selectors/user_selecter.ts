//ors.ts
// import { RootState } from "@/app/store" features/users/usersSelect

import {RootState} from "@/store/store";

export const selectUsers = (state: RootState) => state.users.list
export const selectUsersLoading = (state: RootState) =>
    state.users.loading
export const selectUsersError = (state: RootState) =>
    state.users.error
export const selectSelectedUser = (state: RootState) =>
    state.users.selectedUser


// features/auth/authSelectors.ts

export const selectUser = (state: RootState) => state.auth.user
export const selectToken = (state: RootState) => state.auth.token
export const selectSchoolId = (state: RootState) =>
    state.auth.user?.school_id

/*
export const selectUserRole = (state: RootState) =>
    state.auth.user?.*/
