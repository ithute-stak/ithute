// features/users/usersThunks.ts
import { createAsyncThunk } from "@reduxjs/toolkit"
import * as userAPI from "@/api/auth/user_actions"
import { UserCreate } from "@/types/user"

// GET ALL USERS
export const getUsersThunk = createAsyncThunk(
    "users/getAll",
    async () => {
        return await userAPI.getUsers()
    }
)

// GET SINGLE USER
export const getUserThunk = createAsyncThunk(
    "users/getOne",
    async (id: string) => {
        return await userAPI.getUser(id)
    }
)

// CREATE USER
export const createUserThunk = createAsyncThunk(
    "users/create",
    async (data: UserCreate) => {
        return await userAPI.createUser(data)
    }
)

// UPDATE USER
export const updateUserThunk = createAsyncThunk(
    "users/update",
    async ({
               id,
               data,
           }: {
        id: string
        data: Partial<UserCreate>
    }) => {
        return await userAPI.updateUser(id, data)
    }
)

// DELETE USER
export const deleteUserThunk = createAsyncThunk(
    "users/delete",
    async (id: string) => {
        await userAPI.deleteUser(id)
        return id
    }
)