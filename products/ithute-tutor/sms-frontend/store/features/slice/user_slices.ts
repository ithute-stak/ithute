// features/users/usersSlice.ts
import { createSlice } from "@reduxjs/toolkit"
import { UserResponse } from "@/types/user"
import {
    createUserThunk,
    deleteUserThunk,
    getUsersThunk,
    getUserThunk,
    updateUserThunk
} from "@/store/features/thunks/user_thunks";

interface UsersState {
    list: UserResponse[]
    selectedUser: UserResponse | null
    loading: boolean
    error: string | null
}

const initialState: UsersState = {
    list: [],
    selectedUser: null,
    loading: false,
    error: null,
}

const usersSlice = createSlice({
    name: "users",
    initialState,
    reducers: {
        clearSelectedUser: (state) => {
            state.selectedUser = null
        },
    },
    extraReducers: (builder) => {
        builder

            // GET USERS
            .addCase(getUsersThunk.pending, (state) => {
                state.loading = true
                state.error = null
            })
            .addCase(getUsersThunk.fulfilled, (state, action) => {
                state.loading = false
                state.list = action.payload
            })
            .addCase(getUsersThunk.rejected, (state, action) => {
                state.loading = false
                state.error = action.error.message || "Failed to fetch users"
            })

            // GET ONE USER
            .addCase(getUserThunk.fulfilled, (state, action) => {
                state.selectedUser = action.payload
            })

            // CREATE USER
            .addCase(createUserThunk.fulfilled, (state, action) => {
                state.list.push(action.payload)
            })

            // UPDATE USER
            .addCase(updateUserThunk.fulfilled, (state, action) => {
                const index = state.list.findIndex(
                    (u) => u.id === action.payload.id
                )
                if (index !== -1) {
                    state.list[index] = action.payload
                }

                if (state.selectedUser?.id === action.payload.id) {
                    state.selectedUser = action.payload
                }
            })

            // DELETE USER
            .addCase(deleteUserThunk.fulfilled, (state, action) => {
                state.list = state.list.filter((u) => u.id !== action.payload)

                if (state.selectedUser?.id === action.payload) {
                    state.selectedUser = null
                }
            })
    },
})

export const { clearSelectedUser } = usersSlice.actions
export default usersSlice.reducer