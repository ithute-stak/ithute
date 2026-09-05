// api/finance/feePlan/actions.ts

import api from "@/lib/axios-setup"

import {
    FeePlanCreate,
    FeePlanRead,
    FeePlanUpdate,
} from "@/types/finance/feePlan"
import {FEE_PLAN_ENDPOINTS} from "@/api/finance/feePlan/endpoint";


/* =========================================
   CREATE
========================================= */

export const createFeePlan = async (
    payload: FeePlanCreate
): Promise<FeePlanRead> => {

    const res = await api.post<
        FeePlanRead
    >(
        FEE_PLAN_ENDPOINTS.CREATE,
        payload
    )

    return res.data
}


/* =========================================
   GET ALL
========================================= */

export const getFeePlans = async (): Promise<
    FeePlanRead[]
> => {

    const res = await api.get<
        FeePlanRead[]
    >(
        FEE_PLAN_ENDPOINTS.LIST
    )

    return res.data
}


/* =========================================
   GET ONE
========================================= */

export const getFeePlan = async (
    id: string
): Promise<FeePlanRead> => {

    const res = await api.get<
        FeePlanRead
    >(
        FEE_PLAN_ENDPOINTS.READ(id)
    )

    return res.data
}


/* =========================================
   UPDATE
========================================= */

export const updateFeePlan = async (
    id: string,
    payload: FeePlanUpdate
): Promise<FeePlanRead> => {

    const res = await api.put<
        FeePlanRead
    >(
        FEE_PLAN_ENDPOINTS.UPDATE(id),
        payload
    )

    return res.data
}


/* =========================================
   DELETE
========================================= */

export const deleteFeePlan = async (
    id: string
): Promise<void> => {

    await api.delete(
        FEE_PLAN_ENDPOINTS.DELETE(id)
    )
}