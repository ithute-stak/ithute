// api/student-attendance/endpoint.ts

import { public_api_url } from "@/api/consts";

export const STUDENT_ATTENDANCE_API =
    `${public_api_url}/student-attendance`;

export const STUDENT_ATTENDANCE_ENDPOINTS = {
    LIST: `${STUDENT_ATTENDANCE_API}`,

    CREATE: `${STUDENT_ATTENDANCE_API}`,

    KPI: `${STUDENT_ATTENDANCE_API}/kpi`,

    READ: (id: string) =>
        `${STUDENT_ATTENDANCE_API}/${id}`,

    UPDATE: (id: string) =>
        `${STUDENT_ATTENDANCE_API}/${id}`,

    DELETE: (id: string) =>
        `${STUDENT_ATTENDANCE_API}/${id}`,
};