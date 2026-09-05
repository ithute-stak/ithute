"use client"

import React, { createContext, useContext, useEffect, useMemo } from "react"

import { useAppDispatch, useAppSelector } from "@/store/hooks"
import { StudentRead } from "@/types/student"
import { fetchStudentsThunk } from "@/store/features/thunks/studentThunks"
import { getClassesThunk } from "@/store/features/thunks/classThunks"
import { ClassResponse } from "@/types/classes"
import { fetchTeachersThunk } from "@/store/features/thunks/teacherThunks"
import { TeacherRead } from "@/types/teacher"
import { SchoolResponse } from "@/types/school"
import { getSchoolsThunk } from "@/store/features/thunks/schoolThunks"
import { GradeResponse } from "@/types/grade"
import { getGradesThunk } from "@/store/features/thunks/gradeThunks"
import { FeePlanRead } from "@/types/finance/feePlan"
import { fetchFeePlans } from "@/store/features/thunks/finance/feePlan"
import { SchoolFeeConfigurationRead } from "@/types/finance/schoolFeeConfiguration"
import { fetchSchoolFeeConfigurations } from "@/store/features/thunks/finance/schoolFeeConfiguration/schoolFeeConfigurationThunk"
import { WebSocketProvider } from "@/provider/websocket_provider"
import { NotificationProvider } from "@/provider/notification_provider"

/*
 * IMPORTANT TENANT RULE
 * ---------------------
 * Do not filter operational data with auth.user.school_id here. That field is
 * only a legacy compatibility bridge and is not the selected school for a
 * multi-school user. All collection APIs are already scoped by the server's
 * verified active SchoolContext. School switching performs a hard reload, so
 * Redux state is rebuilt from the newly selected workspace.
 */

type AppDataContextType = {
    students: StudentRead[]
    classes: ClassResponse[]
    teachers: TeacherRead[]
    schools: SchoolResponse[]
    grade: GradeResponse[]
    feePlans: FeePlanRead[]
    schoolFeeConfigs: SchoolFeeConfigurationRead[]
}

const AppDataContext = createContext<AppDataContextType | null>(null)

export function AppDataProvider({ children }: { children: React.ReactNode }) {
    const dispatch = useAppDispatch()
    const user = useAppSelector((state) => state.auth.user)

    const students = useAppSelector((state) => state.students.students)
    const classes = useAppSelector((state) => state.class.classes)
    const teachers = useAppSelector((state) => state.teacher.teachers)
    const schools = useAppSelector((state) => state.schools.schools)
    const grade = useAppSelector((state) => state.grade.grades)
    const feePlans = useAppSelector((state) => state.feePlan.feePlans)
    const schoolFeeConfigs = useAppSelector((state) => state.schoolFeeConfiguration.configurations)

    useEffect(() => {
        if (!user) return
        if (students.length === 0) dispatch(fetchStudentsThunk())
        if (classes.length === 0) dispatch(getClassesThunk())
        if (teachers.length === 0) dispatch(fetchTeachersThunk())
        if (schools.length === 0) dispatch(getSchoolsThunk())
        if (grade.length === 0) dispatch(getGradesThunk())
        if (feePlans.length === 0) dispatch(fetchFeePlans())
        if (schoolFeeConfigs.length === 0) dispatch(fetchSchoolFeeConfigurations())
    }, [
        user,
        students.length,
        classes.length,
        teachers.length,
        schools.length,
        grade.length,
        feePlans.length,
        schoolFeeConfigs.length,
        dispatch,
    ])

    const value = useMemo(
        () => ({ students, classes, teachers, schools, grade, feePlans, schoolFeeConfigs }),
        [students, classes, teachers, schools, grade, feePlans, schoolFeeConfigs],
    )

    return (
        <AppDataContext.Provider value={value}>
            <WebSocketProvider>
                <NotificationProvider>{children}</NotificationProvider>
            </WebSocketProvider>
        </AppDataContext.Provider>
    )
}

export function useAppData() {
    const context = useContext(AppDataContext)
    if (!context) throw new Error("useAppData must be used inside AppDataProvider")
    return context
}
