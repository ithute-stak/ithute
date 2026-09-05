// api/finance/schoolFeeConfiguration/actions.ts

import api from "@/lib/axios-setup"

import {
    SchoolFeeConfigurationCreate,
    SchoolFeeConfigurationRead,
    SchoolFeeConfigurationUpdate,
} from "@/types/finance/schoolFeeConfiguration"
import {SCHOOL_FEE_CONFIGURATION_ENDPOINTS} from "@/api/finance/feeConfig/endpoint";



/* =========================================
   CREATE
========================================= */

export const createSchoolFeeConfiguration = async (
    payload: SchoolFeeConfigurationCreate
): Promise<SchoolFeeConfigurationRead> => {

    const res = await api.post<
        SchoolFeeConfigurationRead
    >(
        SCHOOL_FEE_CONFIGURATION_ENDPOINTS.CREATE,
        payload
    )

    return res.data
}


/* =========================================
   GET ALL
========================================= */

export const getSchoolFeeConfigurations = async (): Promise<
    SchoolFeeConfigurationRead[]
> => {

    const res = await api.get<
        SchoolFeeConfigurationRead[]
    >(
        SCHOOL_FEE_CONFIGURATION_ENDPOINTS.LIST
    )

    return res.data
}


/* =========================================
   GET ONE
========================================= */

export const getSchoolFeeConfiguration = async (
    id: string
): Promise<SchoolFeeConfigurationRead> => {

    const res = await api.get<
        SchoolFeeConfigurationRead
    >(
        SCHOOL_FEE_CONFIGURATION_ENDPOINTS.READ(id)
    )

    return res.data
}


/* =========================================
   UPDATE
========================================= */

export const updateSchoolFeeConfiguration = async (
    id: string,
    payload: SchoolFeeConfigurationUpdate
): Promise<SchoolFeeConfigurationRead> => {

    const res = await api.put<
        SchoolFeeConfigurationRead
    >(
        SCHOOL_FEE_CONFIGURATION_ENDPOINTS.UPDATE(id),
        payload
    )

    return res.data
}


/* =========================================
   DELETE
========================================= */

export const deleteSchoolFeeConfiguration = async (
    id: string
): Promise<void> => {

    await api.delete(
        SCHOOL_FEE_CONFIGURATION_ENDPOINTS.DELETE(id)
    )
}