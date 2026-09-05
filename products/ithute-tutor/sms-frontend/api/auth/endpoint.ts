import { public_api_url } from "@/api/consts";

export const AUTH_API = `${public_api_url}/auth`;
export const USERS_API = `${AUTH_API}/users`;

export const AUTH_ENDPOINTS = {
    OIDC_LOGIN: `${AUTH_API}/oidc/login`,
    LEGACY_LOGIN: `${AUTH_API}/login`,
    LINK_CENTRAL: `${AUTH_API}/link-central`,
    PROVISION_PROFILE: `${public_api_url}/onboarding/profile`,
    REFRESH: `${AUTH_API}/refresh`,
    LOGOUT: `${AUTH_API}/logout`,
    ME: `${AUTH_API}/me`,
};

export const USER_ENDPOINTS = {
    LIST: USERS_API,
    CREATE: USERS_API,
    READ: (id: string) => `${USERS_API}/${id}`,
    UPDATE: (id: string) => `${USERS_API}/${id}`,
    DELETE: (id: string) => `${USERS_API}/${id}`,
};
