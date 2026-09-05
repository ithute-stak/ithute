// types/grade.ts

export interface GradeBase {
    name: string
}

export type GradeCreate = GradeBase

export interface GradeUpdate {
    name?: string
}

export interface GradeResponse extends GradeBase {
    id: string
    created_at?: string | null
    updated_at?: string | null
    created_by?: string | null
    updated_by?: string | null
}

export interface GradeDetailResponse extends GradeResponse {
    school?: Record<string, never> | null
    classes?: Record<string, never>[]
}