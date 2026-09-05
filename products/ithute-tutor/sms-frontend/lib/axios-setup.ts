import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import {refreshAccessToken} from "@/lib/refresh_access_token";

const api = axios.create({
    withCredentials: true,
    timeout: 15000,
});

interface RetryAxiosRequestConfig extends InternalAxiosRequestConfig {
    _retry?: boolean;
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

let isRefreshing = false;
let queue: ((token: string) => void)[] = [];

api.interceptors.response.use(
    (res) => res,

    async (error: AxiosError) => {
        const original = error.config as RetryAxiosRequestConfig;

        if (error.response?.status !== 401 || original._retry) {
            return Promise.reject(error);
        }

        if (isRefreshing) {
            return new Promise((resolve) => {
                queue.push((token) => {
                    original.headers = original.headers ?? {};
                    original.headers.Authorization = `Bearer ${token}`;
                    resolve(api(original));
                });
            });
        }

        original._retry = true;
        isRefreshing = true;

        try {
            const newToken = await refreshAccessToken();

            setToken(newToken);

            queue.forEach((cb) => cb(newToken));
            queue = [];

            original.headers = original.headers ?? {};
            original.headers.Authorization = `Bearer ${newToken}`;

            return api(original);
        } catch (err) {
            setToken(null);
            queue = [];

            if (typeof window !== "undefined") {
                localStorage.removeItem("persist:auth");
                window.location.href = "/login";
            }

            return Promise.reject(err);
        } finally {
            isRefreshing = false;
        }
    }
);

export default api;