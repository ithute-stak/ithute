import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { refreshAccessToken } from "@/lib/refresh_access_token";

const api = axios.create({
    withCredentials: true,
    timeout: 15000,
});

interface TutorAxiosRequestConfig extends InternalAxiosRequestConfig {
    _retry?: boolean;
    skipAuthRefresh?: boolean;
}

/* ---------------- TOKEN INJECTION ---------------- */

let getToken: () => string | null = () => null;
let setToken: (token: string | null) => void = () => {};

export const injectAuth = (opts: {
    getToken: () => string | null;
    setToken: (t: string | null) => void;
}) => {
    getToken = opts.getToken;
    setToken = opts.setToken;
};

/* ---------------- REQUEST INTERCEPTOR ---------------- */

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = getToken();

    if (token) {
        config.headers = config.headers ?? {};
        config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
});

/* ---------------- RESPONSE INTERCEPTOR ---------------- */

// One shared refresh promise prevents refresh storms and guarantees that every
// request waiting on a rotated token resolves or rejects together.
let refreshPromise: Promise<string> | null = null;

function refreshOnce(): Promise<string> {
    if (!refreshPromise) {
        refreshPromise = refreshAccessToken()
            .then((token) => {
                if (!token) throw new Error("Tutor refresh returned no access token");
                setToken(token);
                return token;
            })
            .catch((error) => {
                // Only a definite expired/invalid session clears auth. A temporary
                // central Auth outage must not silently log the user out.
                if (axios.isAxiosError(error) && error.response?.status === 401) {
                    setToken(null);
                }
                throw error;
            })
            .finally(() => {
                refreshPromise = null;
            });
    }

    return refreshPromise;
}

api.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
        const original = error.config as TutorAxiosRequestConfig | undefined;

        if (
            !original ||
            error.response?.status !== 401 ||
            original._retry ||
            original.skipAuthRefresh
        ) {
            return Promise.reject(error);
        }

        original._retry = true;

        try {
            const newToken = await refreshOnce();
            original.headers = original.headers ?? {};
            original.headers.Authorization = `Bearer ${newToken}`;
            return api(original);
        } catch (refreshError) {
            // AuthProvider is the single owner of navigation. The HTTP layer never
            // hard-redirects, avoiding competing login/session redirect loops.
            return Promise.reject(refreshError);
        }
    },
);

export default api;
