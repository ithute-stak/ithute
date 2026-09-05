// types/finance/feePlan.ts

export interface FeePlanBase {
    feeConfig_id: string

    grade_id: string

    name: string

    first_quarter: number

    second_quarter: number

    third_quarter: number

    fourth_quarter: number

    description?: string | null
}

/* =========================================
CREATE
========================================= */

export type FeePlanCreate = FeePlanBase

/* =========================================
UPDATE
========================================= */

export interface FeePlanUpdate {
    grade_id?: string

    name?: string

    first_quarter?: number

    second_quarter?: number

    third_quarter?: number

    fourth_quarter?: number

    description?: string | null
}

/* =========================================
RESPONSE
========================================= */

export interface FeePlanRead
    extends FeePlanBase {
    id: string

    created_at: string

    updated_at: string
}