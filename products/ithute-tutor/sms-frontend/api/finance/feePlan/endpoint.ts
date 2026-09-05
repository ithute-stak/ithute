// api/finance/feePlan/endpoints.ts

import { public_api_url } from "@/api/consts"

export const FEE_PLAN_API =
    `${public_api_url}/fee-plans`

export const FEE_PLAN_ENDPOINTS = {
    LIST: `${FEE_PLAN_API}`,

    CREATE: `${FEE_PLAN_API}`,

    READ: (id: string) =>
        `${FEE_PLAN_API}/${id}`,

    UPDATE: (id: string) =>
        `${FEE_PLAN_API}/${id}`,

    DELETE: (id: string) =>
        `${FEE_PLAN_API}/${id}`,
}