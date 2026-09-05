'use client';

import React, {useEffect, useState} from 'react';
import {motion} from 'framer-motion';
import {
    Users,
    GraduationCap,
    TrendingUp,
    CalendarCheck,
    Search,
    School,
    ArrowUpRight,
    UserCheck,
    Trophy,
    Library,
} from 'lucide-react';

import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';

import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';

import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {useAppData} from "@/provider/dataProvider";
import {StudentRegisterDialog} from "@/app/(dashboard)/dashboard/_components/_person/register_student";
import {AttendanceKPI} from "@/types/student_attendance";
import {getAttendanceKPI} from "@/api/person/student/attendance/actions";
import StudentAttendanceDialog
    from "@/app/(dashboard)/dashboard/(student_management)/students/_components/student_attendance_register";
import Link from "next/link";
import {useWebSocket} from "@/provider/websocket_provider";

const topStudents = [
    {
        name: 'Mpho Seema',
        className: 'Grade 12A',
        performance: 98,
        attendance: 100,
    },
    {
        name: 'Lerato Mohale',
        className: 'Grade 11B',
        performance: 96,
        attendance: 99,
    },
    {
        name: 'Nthabiseng Mota',
        className: 'Grade 10A',
        performance: 95,
        attendance: 98,
    },
    {
        name: 'Kamohelo Nthunya',
        className: 'Grade 9C',
        performance: 93,
        attendance: 97,
    },
];

const activities = [
    {
        title: 'Mid-Year Examinations',
        date: 'Monday • 08:00',
    },
    {
        title: 'Science Fair',
        date: 'Wednesday • 11:00',
    },
    {
        title: 'Parents Consultation',
        date: 'Friday • 14:00',
    },
];

export default function PrincipalStudentsAnalyticsDashboard() {
    const {
        students,
    } = useAppData()
    const [attendanceKpi, setAttendanceKpi] =
        useState<AttendanceKPI | null>(null);

    const analytics = [
        {
            title: 'Total Students',
            value: students.length,
            growth: '+12%',
            icon: Users,
            dialogButton: StudentRegisterDialog,
        },

        {
            title: 'Attendance Rate',
            value: attendanceKpi
                ? `${attendanceKpi.summary.attendance_rate}%`
                : '--',
            growth: '+4%',
            icon: CalendarCheck,
            dialogButton: StudentAttendanceDialog,
        },

        {
            title: 'Present Students',
            value: attendanceKpi
                ? attendanceKpi.summary.present
                : '--',
            growth: '+6%',
            icon: TrendingUp,
            dialogButton: Button,
        },

        {
            title: 'Absent Students',
            value: attendanceKpi
                ? attendanceKpi.summary.absent
                : '--',
            growth: '+3%',
            icon: GraduationCap,
            dialogButton: Button,
        },
    ];
    useEffect(() => {

        async function fetchAttendanceKPI() {

            try {

                const res =
                    await getAttendanceKPI();

                console.log(JSON.stringify(res))

                setAttendanceKpi(res);

            } catch (error) {

                console.error(
                    "Failed to fetch attendance KPI",
                    error
                );
            }
        }

        fetchAttendanceKPI();

    }, []);

    const {
        isConnected,
        lastMessage,
    } = useWebSocket()

    useEffect(() => {

        if (!lastMessage) return

        const event =
            lastMessage.event || lastMessage.type

        switch (event) {

            case "PAYMENT_COMPLETED":
                console.log(
                    "Payment completed:",
                    lastMessage.data
                )
                // refetch finance table
                break

            case "PAYMENT_FAILED":

                console.log(
                    "Payment failed:",
                    lastMessage.data
                )

                break

            case "PAYMENT_REVERSED":

                console.log(
                    "Payment reversed:",
                    lastMessage.data
                )

                break

            case "STUDENT_CREATED":

                console.log(
                    "Student created:",
                    lastMessage.data
                )

                // refetch students
                break

            case "ATTENDANCE_MARKED":

                console.log(
                    "Attendance updated:",
                    lastMessage.data
                )

                break

            default:
                console.log(
                    "Unhandled realtime event:",
                    lastMessage
                )
        }

    }, [lastMessage])

    return (
        <div className="min-h-screen">
            <div className=" space-y-5 p-2 sm:p-3 md:p-4 lg:p-5">
                {/* HEADER */}
                <motion.div
                    initial={{opacity: 0, y: 10}}
                    animate={{opacity: 1, y: 0}}
                    className="rounded-3xl border bg-background p-5 shadow-sm md:p-6"
                >
                    <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
                        <div className="space-y-3">
                            <div
                                className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
                                <School className="h-3.5 w-3.5"/>
                                Principal Student Analytics
                            </div>

                            <div>
                                <h1 className="text-3xl font-bold tracking-tight md:text-4xl">
                                    Students Analytics Dashboard
                                </h1>

                                <p className="mt-2 max-w-3xl text-sm text-muted-foreground md:text-base">
                                    Monitor student academic performance, attendance, behavior,
                                    engagement, and overall institutional progress in real-time.
                                </p>
                            </div>
                        </div>

                        <div className="flex flex-col gap-3 sm:flex-row">
                            <div className="relative">
                                <Search className="absolute left-3 top-3.5 h-4 w-4 text-muted-foreground"/>

                                <Input
                                    placeholder="Search students..."
                                    className="h-11 rounded-2xl pl-10 sm:w-62.5"
                                />
                            </div>

                            <Select>
                                <SelectTrigger className="h-11 w-full rounded-2xl sm:w-45">
                                    <SelectValue placeholder="Select Term"/>
                                </SelectTrigger>

                                <SelectContent>
                                    <SelectItem value="term1">Term 1</SelectItem>
                                    <SelectItem value="term2">Term 2</SelectItem>
                                    <SelectItem value="term3">Term 3</SelectItem>
                                </SelectContent>
                            </Select>

                            <Button className="h-11 rounded-2xl px-6">
                                Generate Report
                            </Button>
                        </div>
                    </div>
                </motion.div>

                {/* ANALYTICS */}
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                    {analytics.map((item, index) => {
                        const Icon = item.icon;

                        return (
                            <motion.div
                                key={item.title}
                                initial={{opacity: 0, y: 20}}
                                animate={{opacity: 1, y: 0}}
                                transition={{delay: index * 0.08}}
                            >
                                <Card
                                    className="rounded-3xl border-0 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-lg">
                                    <CardContent className="p-5">
                                        <div className="flex items-start justify-between">
                                            <div className="space-y-3">
                                                <p className="text-sm text-muted-foreground">
                                                    {item.title}
                                                </p>

                                                <h2 className="text-4xl font-bold tracking-tight">
                                                    {item.value}
                                                </h2>

                                                <div
                                                    className="inline-flex items-center gap-1 rounded-full bg-green-500/10 px-3 py-1 text-xs font-semibold text-green-600">
                                                    <ArrowUpRight className="h-3 w-3"/>
                                                    {item.growth}
                                                </div>
                                            </div>

                                            <div className="space-y-3">
                                                <div className="rounded-2xl bg-primary/10 p-4 text-primary">
                                                   <Link href="/dashboard/students/all">
                                                       <Icon className="h-6 w-6"/>
                                                   </Link>
                                                </div>

                                                <div className="rounded-2xl  p-4 text-primary">
                                                    <item.dialogButton/>
                                                </div>
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>
                            </motion.div>
                        );
                    })}
                </div>

                {/* MAIN GRID */}
                <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
                    {/* STUDENT TABLE */}
                    <Card className=" xl:col-span-2 rounded-3xl border-0 shadow-sm">
                        <CardHeader>
                            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                                <div>
                                    <CardTitle className="text-xl">
                                        Top Performing Students
                                    </CardTitle>

                                    <CardDescription className="mt-1">
                                        Detailed overview of high-performing students.
                                    </CardDescription>
                                </div>

                                <Button variant="outline" className="rounded-2xl">
                                    View Full Report
                                </Button>
                            </div>
                        </CardHeader>

                        <CardContent>
                            <div className="overflow-x-auto">
                                <table className="w-full min-w-187.5">
                                    <thead>
                                    <tr className="border-b text-left">
                                        <th className="pb-4 font-semibold">Student</th>
                                        <th className="pb-4 font-semibold">Class</th>
                                        <th className="pb-4 font-semibold">Performance</th>
                                        <th className="pb-4 font-semibold">Attendance</th>
                                        <th className="pb-4 font-semibold">Status</th>
                                    </tr>
                                    </thead>

                                    <tbody>
                                    {topStudents.map((student, index) => (
                                        <motion.tr
                                            key={student.name}
                                            initial={{opacity: 0}}
                                            animate={{opacity: 1}}
                                            transition={{delay: index * 0.06}}
                                            className="border-b last:border-none"
                                        >
                                            <td className="py-5">
                                                <div className="flex items-center gap-3">
                                                    <div
                                                        className="flex h-11 w-11 items-center justify-center rounded-full bg-primary/10 font-semibold text-primary">
                                                        {student.name.charAt(0)}
                                                    </div>

                                                    <div>
                                                        <p className="font-semibold">{student.name}</p>

                                                        <p className="text-sm text-muted-foreground">
                                                            Student
                                                        </p>
                                                    </div>
                                                </div>
                                            </td>

                                            <td className="py-5">{student.className}</td>

                                            <td className="py-5">
                                                <div className="flex items-center gap-3">
                                                    <div className="h-2 w-32 overflow-hidden rounded-full bg-muted">
                                                        <div
                                                            className="h-full rounded-full bg-primary"
                                                            style={{
                                                                width: `${student.performance}%`,
                                                            }}
                                                        />
                                                    </div>

                                                    <span className="font-medium">
                            {student.performance}%
                          </span>
                                                </div>
                                            </td>

                                            <td className="py-5">
                                                {student.attendance}%
                                            </td>

                                            <td className="py-5">
                                                <div
                                                    className="inline-flex items-center gap-1 rounded-full bg-green-500/10 px-3 py-1 text-xs font-semibold text-green-600">
                                                    <Trophy className="h-3 w-3"/>
                                                    Excellent
                                                </div>
                                            </td>
                                        </motion.tr>
                                    ))}
                                    </tbody>
                                </table>
                            </div>
                        </CardContent>
                    </Card>
                    {/* ACTIVITIES */}
                    <div className="space-y-4">
                        <Card className="rounded-3xl border-0 shadow-sm">
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2 text-lg">
                                    <UserCheck className="h-5 w-5"/>
                                    Attendance Insights
                                </CardTitle>
                            </CardHeader>

                            <CardContent className="space-y-5">
                                {[
                                    {
                                        label: 'Attendance Rate',
                                        value:
                                            attendanceKpi?.summary
                                                ?.attendance_rate || 0,
                                    },
                                    {
                                        label: 'Late Arrivals',
                                        value:
                                            attendanceKpi
                                                ?.status_distribution
                                                ?.late || 0,
                                    },
                                    {
                                        label: 'Absentees',
                                        value:
                                            attendanceKpi
                                                ?.status_distribution
                                                ?.absent || 0,
                                    },
                                ].map((item) => (
                                    <div
                                        key={item.label}
                                        className="space-y-2"
                                    >
                                        <div className="flex items-center justify-between text-sm">
                                            <span>{item.label}</span>

                                            <span className="font-semibold">
                        {item.label ===
                        'Attendance Rate'
                            ? `${item.value}%`
                            : item.value}
                    </span>
                                        </div>

                                        <div className="h-3 overflow-hidden rounded-full bg-muted">
                                            <motion.div
                                                initial={{width: 0}}
                                                animate={{
                                                    width: `${
                                                        item.label ===
                                                        'Attendance Rate'
                                                            ? item.value
                                                            : Math.min(
                                                                item.value * 10,
                                                                100
                                                            )
                                                    }%`,
                                                }}
                                                transition={{
                                                    duration: 0.8,
                                                }}
                                                className="h-full rounded-full bg-primary"
                                            />
                                        </div>
                                    </div>
                                ))}
                            </CardContent>
                        </Card>
                        <Card className="rounded-3xl border-0 shadow-sm">
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2 text-lg">
                                    <Library className="h-5 w-5"/>
                                    Subject Performance
                                </CardTitle>
                            </CardHeader>

                            <CardContent className="space-y-4">
                                {[
                                    'Mathematics',
                                    'Science',
                                    'English',
                                    'History',
                                    'Geography',
                                ].map((subject) => (
                                    <div
                                        key={subject}
                                        className="flex items-center justify-between rounded-2xl border p-4"
                                    >
                                        <span className="font-medium">{subject}</span>

                                        <span
                                            className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                    Strong
                  </span>
                                    </div>
                                ))}
                            </CardContent>
                        </Card>
                    </div>
                </div>
            </div>
        </div>
    );
}