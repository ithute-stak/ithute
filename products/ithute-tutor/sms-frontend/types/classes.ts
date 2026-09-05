// types/class.ts

export interface ClassBase {
    name: string // A, B, C
    grade_id: string
    school_id: string
}

export type ClassCreate = ClassBase

export interface ClassUpdate {
    name?: string
    grade_id?: string
    school_id?: string
}

export interface ClassResponse extends ClassBase {
    id: string
    created_at?: string | null
    updated_at?: string | null
    created_by?: string | null
    updated_by?: string | null
}

export interface ClassDetailResponse extends ClassResponse {
    grade?: Record<string, never> | null
    school?: Record<string, never> | null
    students?: Record<string, never>[]
}