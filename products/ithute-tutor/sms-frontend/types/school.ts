export enum SchoolCategory {
    pre_school = "pre_school",
    junior_school = "junior_school",
    primary_school = "primary_school",
    basic_education_school = "basic_education_school",
    secondary_school = "secondary_school",
    high_school = "high_school",
    junior_college = "junior_college",
    learning_center = "learning_center",
}

/* =========================
BASE
========================= */

export interface SchoolBase {
    name: string
    school_code?: string | null
    registration_number?: string | null
    category: SchoolCategory
}

/* =========================
CREATE
========================= */

export interface SchoolCreate extends SchoolBase {}

/* =========================
UPDATE
========================= */

export interface SchoolUpdate {
    name?: string
    school_code?: string | null
    registration_number?: string | null
    category?: SchoolCategory
    is_registered?: boolean
    certificate_number?: string | null
}

/* =========================
RESPONSE
========================= */

export interface SchoolResponse extends SchoolBase {
    id: string
    is_registered?: boolean | null
    certificate_number?: string | null

    proprietor?: Record<string, never> | null
    contact_person?: Record<string, never> | null
}