import { AUTH_ENDPOINTS } from "@/api/auth/endpoint";
import api from "@/lib/axios-setup";

export const beginCentralLogin = () => {
    if (typeof window !== "undefined") {
        window.location.assign(AUTH_ENDPOINTS.OIDC_LOGIN);
    }
};

export const linkCentralAccount = async (email: string, password: string) => {
    const response = await api.post(
        AUTH_ENDPOINTS.LINK_CENTRAL,
        { email, password },
        { withCredentials: true },
    );
    return response.data;
};

export const provisionTutorProfile = async (username: string, email: string) => {
    const response = await api.post(
        AUTH_ENDPOINTS.PROVISION_PROFILE,
        { username, email },
        { withCredentials: true },
    );
    return response.data;
};

export const refreshToken = async () => {
    const response = await api.post(
        AUTH_ENDPOINTS.REFRESH,
        {},
        { withCredentials: true },
    );
    return response.data;
};

export const logout = async () => {
    const response = await api.post(
        AUTH_ENDPOINTS.LOGOUT,
        {},
        { withCredentials: true },
    );
    return response.data;
};

export const getCurrentUser = async () => {
    const response = await api.get(
        AUTH_ENDPOINTS.ME,
        { withCredentials: true },
    );
    return response.data;
};
