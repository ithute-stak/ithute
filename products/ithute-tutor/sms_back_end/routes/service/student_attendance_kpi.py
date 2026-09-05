# services/student_attendance_kpi.py

from collections import defaultdict
from datetime import date


def build_student_attendance_kpi(
    attendance_records
):
    # =========================
    # Get attendance average
    # =========================

    

    # =========================
    # MAIN COUNTERS
    # =========================

    total_records = len(attendance_records)

    total_present = 0
    total_absent = 0
    total_late = 0

    # =========================
    # CHART DATA
    # =========================

    monthly_attendance = defaultdict(int)

    daily_attendance = defaultdict(
        lambda: {
            "present": 0,
            "absent": 0,
            "late": 0
        }
    )

    classroom_attendance = defaultdict(
        lambda: {
            "present": 0,
            "absent": 0,
            "late": 0,
            "total": 0
        }
    )

    student_attendance = defaultdict(
        lambda: {
            "present": 0,
            "absent": 0,
            "late": 0,
            "total": 0
        }
    )

    # =========================
    # LOOP
    # =========================

    for record in attendance_records:

        status = (
            record.status.lower()
            if record.status
            else "present"
        )

        attendance_date = (
            record.attendance_date
        )

        student_name = "Unknown"

        if (
            record.student
            and record.student.user.person
        ):

            first_name = (
                record.student.user.person.first_name
                or ""
            )

            last_name = (
                record.student.user.person.last_name
                or ""
            )

            student_name = (
                f"{first_name} {last_name}"
                .strip()
            )

        classroom_name = "Unknown"

        if record.classroom:

            classroom_name = (
                record.classroom.name
                or "Unknown"
            )

        # =========================
        # STATUS COUNTS
        # =========================

        if status == "present":
            total_present += 1

        elif status == "absent":
            total_absent += 1

        elif status == "late":
            total_late += 1

        # =========================
        # MONTHLY CHART
        # =========================

        if attendance_date:

            month_key = (
                attendance_date.strftime(
                    "%Y-%m"
                )
            )

            monthly_attendance[
                month_key
            ] += 1

            day_key = (
                attendance_date.strftime(
                    "%Y-%m-%d"
                )
            )

            daily_attendance[
                day_key
            ][status] += 1

        # =========================
        # CLASSROOM KPI
        # =========================

        classroom_attendance[
            classroom_name
        ][status] += 1

        classroom_attendance[
            classroom_name
        ]["total"] += 1

        # =========================
        # STUDENT KPI
        # =========================

        student_attendance[
            student_name
        ][status] += 1

        student_attendance[
            student_name
        ]["total"] += 1

    # =========================
    # ATTENDANCE RATE
    # =========================

    attendance_rate = 0

    if total_records > 0:

        attendance_rate = round(
            (
                total_present
                / total_records
            ) * 100,
            2
        )

    # =========================
    # TOP ABSENT STUDENTS
    # =========================

    top_absent_students = []

    for (
        student,
        stats
    ) in student_attendance.items():

        top_absent_students.append({
            "student": student,
            "absent": stats["absent"],
            "late": stats["late"],
            "present": stats["present"],
            "total": stats["total"]
        })

    top_absent_students = sorted(
        top_absent_students,
        key=lambda x: x["absent"],
        reverse=True
    )[:10]

    # =========================
    # CLASSROOM PERFORMANCE
    # =========================

    classroom_performance = []

    for (
        classroom,
        stats
    ) in classroom_attendance.items():

        total = stats["total"]

        rate = 0

        if total > 0:

            rate = round(
                (
                    stats["present"]
                    / total
                ) * 100,
                2
            )

        classroom_performance.append({
            "classroom": classroom,
            "attendance_rate": rate,
            "present": stats["present"],
            "absent": stats["absent"],
            "late": stats["late"],
            "total": total
        })

    classroom_performance = sorted(
        classroom_performance,
        key=lambda x: x["attendance_rate"],
        reverse=True
    )

    # =========================
    # RETURN
    # =========================

    return {

        # =====================
        # SUMMARY CARDS
        # =====================

        "summary": {

            "total_records": total_records,

            "present": total_present,

            "absent": total_absent,

            "late": total_late,

            "attendance_rate": attendance_rate
        },

        # =====================
        # BAR / LINE CHART
        # =====================

        "monthly_attendance_chart": [

            {
                "month": month,
                "records": count
            }

            for month, count
            in sorted(
                monthly_attendance.items()
            )
        ],

        # =====================
        # DAILY TREND
        # =====================

        "daily_attendance_chart": [

            {
                "date": day,

                "present": values["present"],

                "absent": values["absent"],

                "late": values["late"]
            }

            for day, values
            in sorted(
                daily_attendance.items()
            )
        ],

        # =====================
        # PIE CHART
        # =====================

        "status_distribution": {

            "present": total_present,

            "absent": total_absent,

            "late": total_late
        },

        # =====================
        # TABLE
        # =====================

        "top_absent_students":
            top_absent_students,

        # =====================
        # CLASSROOM ANALYTICS
        # =====================

        "classroom_performance":
            classroom_performance
    }