// types/student-attendance.ts

export type AttendanceStatus =
    | "present"
    | "absent"
    | "late";



/* ========================================
   CREATE
======================================== */

export interface StudentAttendanceCreate {
    student_id: string;

    classroom_id?: string | null;

    attendance_date: string;

    status: AttendanceStatus;

    remarks?: string | null;
}



/* ========================================
   UPDATE
======================================== */

export interface StudentAttendanceUpdate {
    classroom_id?: string | null;

    attendance_date?: string;

    status?: AttendanceStatus;

    remarks?: string | null;
}



/* ========================================
   RESPONSE
======================================== */

export interface StudentAttendanceRead {
    id: string;

    student_id: string;

    classroom_id?: string | null;

    attendance_date: string;

    status: AttendanceStatus;

    remarks?: string | null;

    created_at: string;

    updated_at: string;
}



/* ========================================
   KPI
======================================== */
export interface AttendanceKPI {
    summary: {
        total_records: number;

        present: number;

        absent: number;

        late: number;

        attendance_rate: number;
    };

    monthly_attendance_chart: {
        month: string;
        attendance: number;
    }[];

    daily_attendance_chart: {
        day: string;
        attendance: number;
    }[];

    status_distribution: {
        present: number;

        absent: number;

        late: number;
    };

    top_absent_students: {
        student_name: string;

        total_absent: number;
    }[];

    classroom_performance: {
        classroom: string;

        attendance_rate: number;
    }[];
}