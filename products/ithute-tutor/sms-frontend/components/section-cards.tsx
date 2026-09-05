"use client"

import {Badge} from "@/components/ui/badge"
import {
    Card,
    CardAction,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"

import {
    Users,
    School,
    GraduationCap,
    TrendingUp,
    TrendingDown,
    BookOpen,
} from "lucide-react"
import {useAppDispatch, useAppSelector} from "@/store/hooks";
import {SchoolRegisterDialog} from "@/app/(dashboard)/dashboard/_components/school_registration";
import {useEffect} from "react";
import {getClassesThunk} from "@/store/features/thunks/classThunks";
import {getSchoolsThunk} from "@/store/features/thunks/schoolThunks";
import {TeacherRegisterDialog} from "@/app/(dashboard)/dashboard/_components/_person/register_teacher";
import {fetchTeachersThunk} from "@/store/features/thunks/teacherThunks";
import {fetchStudentsThunk} from "@/store/features/thunks/studentThunks";
import {StudentRegisterDialog} from "@/app/(dashboard)/dashboard/_components/_person/register_student";
import {ClassRegisterDialog} from "@/app/(dashboard)/dashboard/_components/class_grade";
import {UserRole} from "@/types/shared.primitive";
import {useAppData} from "@/provider/dataProvider";

export function SectionCards() {
    const dispatch = useAppDispatch()
    const {students, classes, teachers} = useAppData()
    const {schools} = useAppSelector(
        (state) => state.schools
    );
    useEffect(() => {
        if (schools.length <= 0) {
            dispatch(getSchoolsThunk())
        }


    }, [dispatch, schools.length]);
    return (
        <div className="grid grid-cols-1 gap-4 px-4 lg:px-6 @xl/main:grid-cols-2 @5xl/main:grid-cols-4">

            {/* TOTAL STUDENTS */}
            <Card className="@container/card">
                <CardHeader>
                    <CardDescription>Total Students</CardDescription>

                    <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                        {students.filter((q)=>q.user.role===UserRole.student).length}
                    </CardTitle>

                    <CardAction>
                        <Badge variant="outline">
                            <TrendingUp className="size-4"/>
                            +8.2%
                        </Badge>
                    </CardAction>
                </CardHeader>

                <CardFooter className="flex items-center justify-between gap-4 text-sm">
                    <div className="flex flex-col gap-1.5">
                        <div className="flex gap-2 font-medium">
                            Student enrollment growing
                            <Users className="size-4"/>
                        </div>
                        <div className="text-muted-foreground">
                            Compared to last academic term
                        </div>
                    </div>
                    <StudentRegisterDialog/>
                </CardFooter>
            </Card>

            {/* TOTAL SCHOOLS */}
            <Card className="@container/card">
                <CardHeader>
                    <CardDescription>Registered Schools</CardDescription>

                    <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                        {schools.length}
                    </CardTitle>

                    <CardAction>
                        <Badge variant="outline">
                            <TrendingUp className="size-4"/>
                            +1
                        </Badge>
                    </CardAction>
                </CardHeader>

                <CardFooter className="flex items-center justify-between gap-4 text-sm">

                    {/* LEFT SIDE (INFO) */}
                    <div className="flex flex-col gap-1.5">
                        <div className="flex gap-2 font-medium">
                            New school onboarded
                            <School className="size-4"/>
                        </div>
                        <div className="text-muted-foreground">
                            Across all districts
                        </div>
                    </div>

                    {/* RIGHT SIDE (ACTION) */}
                    <SchoolRegisterDialog/>

                </CardFooter>
            </Card>

            {/* CLASSES */}
            <Card className="@container/card">
                <CardHeader>
                    <CardDescription>Total Classes</CardDescription>

                    <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                        {classes.length}
                    </CardTitle>

                    <CardAction>
                        <Badge variant="outline">
                            <TrendingUp className="size-4"/>
                            +5.4%
                        </Badge>
                    </CardAction>
                </CardHeader>

                <CardFooter className="flex items-center justify-between gap-4 text-sm">
                    <div className="flex flex-col gap-1.5">
                        <div className="flex gap-2 font-medium">
                            More classes added
                            <BookOpen className="size-4"/>
                        </div>
                        <div className="text-muted-foreground">
                            Grade 1A, 1B, 2A, 2B structure
                        </div>
                    </div>
                    <ClassRegisterDialog/>
                </CardFooter>
            </Card>

            {/* TEACHERS / PERFORMANCE */}
            <Card className="@container/card">
                <CardHeader>
                    <CardDescription>Active Teachers</CardDescription>

                    <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                        {teachers.length}
                    </CardTitle>

                    <CardAction>
                        <Badge variant="outline">
                            <TrendingDown className="size-4"/>
                            -2.1%
                        </Badge>
                    </CardAction>
                </CardHeader>

                <CardFooter className="flex items-center justify-between gap-4 text-sm">
                    <div className="flex flex-col gap-1.5">
                        <div className="flex gap-2 font-medium">
                            Slight decrease in staffing
                            <GraduationCap className="size-4"/>
                        </div>
                        <div className="text-muted-foreground">
                            Needs recruitment attention
                        </div>
                    </div>

                    <TeacherRegisterDialog/>
                </CardFooter>
            </Card>
        </div>
    )
}