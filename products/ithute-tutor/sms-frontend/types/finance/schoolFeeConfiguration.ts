// types/finance/endpoint.ts

export type FeeStructureType =
    | 'quarterly'
    | 'monthly'
    | 'annual'

/* =========================================
   BASE
========================================= */

export interface SchoolFeeConfigurationBase {
    school_id: string

    year_start: string

    year_end: string

    fee_structure: FeeStructureType

    allow_partial_payments: boolean

    allow_late_payments: boolean
}

/* =========================================
   CREATE
========================================= */

export type SchoolFeeConfigurationCreate = SchoolFeeConfigurationBase

/* =========================================
   UPDATE
========================================= */

export interface SchoolFeeConfigurationUpdate {
    year_start?: string

    year_end?: string

    fee_structure?: FeeStructureType

    allow_partial_payments?: boolean

    allow_late_payments?: boolean
}

/* =========================================
   RESPONSE
========================================= */

export interface SchoolFeeConfigurationRead
    extends SchoolFeeConfigurationBase {

    id: string

    created_at: string

    updated_at: string
}