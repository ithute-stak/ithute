import axios from "axios";
import {AUTH_ENDPOINTS} from "@/api/auth/endpoint";
import {RefreshResponse} from "@/types/user";


const refreshClient = axios.create({
    withCredentials: true,
});

export async function refreshAccessToken(): Promise<string> {
    const res = await refreshClient.post<RefreshResponse>(
        AUTH_ENDPOINTS.REFRESH
    );

    return res.data.access_token;
}