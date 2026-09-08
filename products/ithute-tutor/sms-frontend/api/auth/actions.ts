import { AUTH_ENDPOINTS } from "@/api/auth/endpoint";
import api from "@/lib/axios-setup";

export const beginCentralLogin = () => {
    if (typeof window !== "undefined") {
        // Replace the local login entry instead of adding another history entry.
        // This prevents browser-back/login bounce after the central OIDC round-trip.
        window.location.replace(AUTH_ENDPOINTS.OIDC_LOGIN);
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
        { withCredentials: true, skipAuthRefresh: true },
    );
    return response.data;
};

export const logout = async () => {
    const response = await api.post(
        AUTH_ENDPOINTS.LOGOUT,
        {},
        // Logout is deliberately never refreshed/retried. It must remain an
        // idempotent local session-clear operation even if central Auth expired.
        { withCredentials: true, skipAuthRefresh: true },
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
