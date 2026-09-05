// api/finance/schoolFeeConfiguration/endpoints.ts

import { public_api_url } from "@/api/consts"

export const SCHOOL_FEE_CONFIGURATION_API =
    `${public_api_url}/school-fee-configurations`

export const SCHOOL_FEE_CONFIGURATION_ENDPOINTS = {
    LIST: `${SCHOOL_FEE_CONFIGURATION_API}`,

    CREATE: `${SCHOOL_FEE_CONFIGURATION_API}`,

    READ: (id: string) =>
        `${SCHOOL_FEE_CONFIGURATION_API}/${id}`,

    UPDATE: (id: string) =>
        `${SCHOOL_FEE_CONFIGURATION_API}/${id}`,

    DELETE: (id: string) =>
        `${SCHOOL_FEE_CONFIGURATION_API}/${id}`,
}