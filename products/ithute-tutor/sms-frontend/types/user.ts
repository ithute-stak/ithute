import {PersonCreate, PersonRead} from "@/types/person";
import {UserRole, UUID} from "@/types/shared.primitive";



/* =========================
LOGIN
========================= */
export interface RefreshResponse {
    access_token: string;
    token_type: string;
}

export interface UserLogin {
    email: string
    password: string
}

export interface UserAuthResponse {
    id: string
    email: string
    name: string
    role:UserRole
    school_id?: string | null
}

export interface LoginResponse {
    access_token: string
    token_type: string
    user: UserAuthResponse
}

/* =========================
REFRESH TOKEN
========================= */

export interface RefreshTokenOut {
    id: string
    jti: string
    revoked: boolean
    expires_at: string
    created_at: string
}

/* =========================
USER
========================= */

export interface UserBase {
    username: string
    email: string
    role: UserRole
    school_id?: string | null
}


export interface UserUpdate {
    username?: string
    email?: string
    password?: string
    role?: UserRole
    school_id?: string | null
}

export interface UserResponse extends UserBase {
    id: string
}




export interface UserCreate {
    username: string;
    email: string;
    password: string;
    role: UserRole;
    school_id?: UUID | null;
    person:PersonCreate
}

export interface UserRead {
    id: UUID;
    username: string;
    email: string;
    role: UserRole;
    school_id?: UUID | null;
    person?: PersonRead | null;
}