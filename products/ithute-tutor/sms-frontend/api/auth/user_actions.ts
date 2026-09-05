

import { UserCreate, UserResponse } from "@/types/user"
import {USER_ENDPOINTS} from "@/api/auth/endpoint";
import api from "@/lib/axios-setup";

export const createUser = async (data: UserCreate) => {
    const res = await api.post<UserResponse>(
        USER_ENDPOINTS.CREATE,
        data
    )

    return res.data
}

export const getUsers = async () => {
    const res = await api.get<UserResponse[]>(
        USER_ENDPOINTS.LIST
    )

    return res.data
}

export const getUser = async (id: string) => {
    const res = await api.get<UserResponse>(
        USER_ENDPOINTS.READ(id)
    )

    return res.data
}

export const updateUser = async (
    id: string,
    data: Partial<UserCreate>
) => {
    const res = await api.put<UserResponse>(
        USER_ENDPOINTS.UPDATE(id),
        data
    )

    return res.data
}

export const deleteUser = async (id: string) => {
    const res = await api.delete(
        USER_ENDPOINTS.DELETE(id)
    )

    return res.data
}