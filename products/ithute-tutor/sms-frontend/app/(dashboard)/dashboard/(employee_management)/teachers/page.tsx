'use client';

import React from 'react';
import { motion } from 'framer-motion';
import {
    Users,
    GraduationCap,
    TrendingUp,
    CalendarCheck,
    ClipboardList,
    BookOpen,
    Bell,
    Search,
    Award,
    Activity,
    School,
    Clock3,
    ArrowUpRight,
    ArrowDownRight,
} from 'lucide-react';

import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';

const analytics = [
    {
        title: 'Total Teachers',
        value: '84',
        growth: '+8%',
        positive: true,
        icon: Users,
    },
    {
        title: 'Average Performance',
        value: '91%',
        growth: '+4%',
        positive: true,
        icon: TrendingUp,
    },
    {
        title: 'Attendance Rate',
        value: '96%',
        growth: '+2%',
        positive: true,
        icon: CalendarCheck,
    },
    {
        title: 'Late Submissions',
        value: '14',
        growth: '-5%',
        positive: false,
        icon: ClipboardList,
    },
];

const teacherPerformance = [
    {
        name: 'Mrs. Mpho Seema',
        subject: 'Mathematics',
        className: 'Grade 7A',
        performance: 96,
        attendance: 98,
    },
    {
        name: 'Mr. Lerato Mohale',
        subject: 'Science',
        className: 'Grade 8B',
        performance: 92,
        attendance: 95,
    },
    {
        name: 'Mrs. Nthabiseng Mota',
        subject: 'English',
        className: 'Grade 9C',
        performance: 89,
        attendance: 94,
    },
    {
        name: 'Mr. Kamohelo Nthunya',
        subject: 'Geography',
        className: 'Grade 6A',
        performance: 87,
        attendance: 90,
    },
];

const upcomingActivities = [
    {
        title: 'Teacher Evaluation Meeting',
        date: 'Monday • 10:00',
    },
    {
        title: 'Academic Performance Review',
        date: 'Wednesday • 13:00',
    },
    {
        title: 'Staff Development Workshop',
        date: 'Friday • 09:00',
    },
];

const weeklyPerformance = [82, 91, 76, 95, 88, 93, 97];
const weekDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export default function PrincipalTeacherAnalyticsDashboard() {
    return (
        <div className="min-h-screen">
            <div className="space-y-5 p-2 sm:p-3 md:p-4 lg:p-5">
                {/* HEADER */}
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="rounded-3xl border bg-background p-5 shadow-sm md:p-6"
                >
                    <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
                        <div className="space-y-3">
                            <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
                                <School className="h-3.5 w-3.5" />
                                Principal Analytics Center
                            </div>

                            <div>
                                <h1 className="text-3xl font-bold tracking-tight md:text-4xl">
                                    Teachers Analytics Dashboard
                                </h1>

                                <p className="mt-2 max-w-3xl text-sm text-muted-foreground md:text-base">
                                    Monitor teacher performance, attendance, classroom activity,
                                    assignments, academic outcomes, and institutional growth in
                                    real-time.
                                </p>
                            </div>
                        </div>

                        <div className="flex flex-col gap-3 sm:flex-row">
                            <div className="relative">
                                <Search className="absolute left-3 top-3.5 h-4 w-4 text-muted-foreground" />

                                <Input
                                    placeholder="Search teachers..."
                                    className="h-11 rounded-2xl pl-10 sm:w-[250px]"
                                />
                            </div>

                            <Select>
                                <SelectTrigger className="h-11 w-full rounded-2xl sm:w-[180px]">
                                    <SelectValue placeholder="Select Term" />
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
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: index * 0.08 }}
                            >
                                <Card className="rounded-3xl border-0 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-lg">
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
                                                    className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold ${
                                                        item.positive
                                                            ? 'bg-green-500/10 text-green-600'
                                                            : 'bg-red-500/10 text-red-600'
                                                    }`}
                                                >
                                                    {item.positive ? (
                                                        <ArrowUpRight className="h-3 w-3" />
                                                    ) : (
                                                        <ArrowDownRight className="h-3 w-3" />
                                                    )}

                                                    {item.growth}
                                                </div>
                                            </div>

                                            <div className="rounded-2xl bg-primary/10 p-4 text-primary">
                                                <Icon className="h-6 w-6" />
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
                    {/* PERFORMANCE CHART */}
                    <Card className="xl:col-span-2 rounded-3xl border-0 shadow-sm">
                        <CardHeader>
                            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                                <div>
                                    <CardTitle className="text-xl">
                                        Weekly Teacher Performance
                                    </CardTitle>

                                    <CardDescription className="mt-1">
                                        Overall teacher effectiveness and classroom productivity.
                                    </CardDescription>
                                </div>

                                <Select>
                                    <SelectTrigger className="w-[170px] rounded-2xl">
                                        <SelectValue placeholder="This Week" />
                                    </SelectTrigger>

                                    <SelectContent>
                                        <SelectItem value="week">This Week</SelectItem>
                                        <SelectItem value="month">This Month</SelectItem>
                                        <SelectItem value="year">This Year</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        </CardHeader>

                        <CardContent>
                            <div className="flex h-[320px] items-end gap-3 rounded-3xl bg-muted/40 p-4">
                                {weeklyPerformance.map((value, index) => (
                                    <div
                                        key={index}
                                        className="flex flex-1 flex-col items-center gap-3"
                                    >
                                        <motion.div
                                            initial={{ height: 0 }}
                                            animate={{ height: `${value * 2.5}px` }}
                                            transition={{
                                                duration: 0.7,
                                                delay: index * 0.08,
                                            }}
                                            className="w-full rounded-t-3xl bg-primary"
                                        />

                                        <span className="text-xs font-medium text-muted-foreground">
                      {weekDays[index]}
                    </span>
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>

                    {/* UPCOMING */}
                    <Card className="rounded-3xl border-0 shadow-sm">
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2 text-xl">
                                <Bell className="h-5 w-5" />
                                Upcoming Activities
                            </CardTitle>

                            <CardDescription>
                                School management and teacher schedules.
                            </CardDescription>
                        </CardHeader>

                        <CardContent className="space-y-4">
                            {upcomingActivities.map((activity, index) => (
                                <motion.div
                                    key={activity.title}
                                    initial={{ opacity: 0, x: 15 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: index * 0.08 }}
                                    className="rounded-2xl border bg-muted/30 p-4 transition-all hover:bg-muted/50"
                                >
                                    <div className="flex items-start justify-between">
                                        <div className="space-y-1">
                                            <h3 className="font-semibold">{activity.title}</h3>

                                            <p className="text-sm text-muted-foreground">
                                                {activity.date}
                                            </p>
                                        </div>

                                        <div className="rounded-xl bg-primary/10 p-2 text-primary">
                                            <Clock3 className="h-4 w-4" />
                                        </div>
                                    </div>
                                </motion.div>
                            ))}
                        </CardContent>
                    </Card>
                </div>

                {/* TEACHERS TABLE */}
                <Card className="rounded-3xl border-0 shadow-sm">
                    <CardHeader>
                        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                            <div>
                                <CardTitle className="text-xl">
                                    Teacher Performance Overview
                                </CardTitle>

                                <CardDescription className="mt-1">
                                    Detailed analysis of teacher performance and attendance.
                                </CardDescription>
                            </div>

                            <Button variant="outline" className="rounded-2xl">
                                View Full Report
                            </Button>
                        </div>
                    </CardHeader>

                    <CardContent>
                        <div className="overflow-x-auto">
                            <table className="w-full min-w-[750px]">
                                <thead>
                                <tr className="border-b text-left">
                                    <th className="pb-4 font-semibold">Teacher</th>
                                    <th className="pb-4 font-semibold">Subject</th>
                                    <th className="pb-4 font-semibold">Class</th>
                                    <th className="pb-4 font-semibold">Performance</th>
                                    <th className="pb-4 font-semibold">Attendance</th>
                                    <th className="pb-4 font-semibold">Status</th>
                                </tr>
                                </thead>

                                <tbody>
                                {teacherPerformance.map((teacher, index) => (
                                    <motion.tr
                                        key={teacher.name}
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        transition={{ delay: index * 0.06 }}
                                        className="border-b last:border-none"
                                    >
                                        <td className="py-5">
                                            <div className="flex items-center gap-3">
                                                <div className="flex h-11 w-11 items-center justify-center rounded-full bg-primary/10 font-semibold text-primary">
                                                    {teacher.name.charAt(0)}
                                                </div>

                                                <div>
                                                    <p className="font-semibold">{teacher.name}</p>

                                                    <p className="text-sm text-muted-foreground">
                                                        Teacher
                                                    </p>
                                                </div>
                                            </div>
                                        </td>

                                        <td className="py-5">{teacher.subject}</td>

                                        <td className="py-5">{teacher.className}</td>

                                        <td className="py-5">
                                            <div className="flex items-center gap-3">
                                                <div className="h-2 w-32 overflow-hidden rounded-full bg-muted">
                                                    <div
                                                        className="h-full rounded-full bg-primary"
                                                        style={{
                                                            width: `${teacher.performance}%`,
                                                        }}
                                                    />
                                                </div>

                                                <span className="font-medium">
                            {teacher.performance}%
                          </span>
                                            </div>
                                        </td>

                                        <td className="py-5">
                                            {teacher.attendance}%
                                        </td>

                                        <td className="py-5">
                                            <div className="inline-flex items-center gap-1 rounded-full bg-green-500/10 px-3 py-1 text-xs font-semibold text-green-600">
                                                <Award className="h-3 w-3" />
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

                {/* BOTTOM */}
                <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
                    <Card className="rounded-3xl border-0 shadow-sm">
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2 text-lg">
                                <GraduationCap className="h-5 w-5" />
                                Academic Quality
                            </CardTitle>
                        </CardHeader>

                        <CardContent className="space-y-5">
                            {[
                                {
                                    label: 'Lesson Completion',
                                    value: 94,
                                },
                                {
                                    label: 'Exam Preparation',
                                    value: 89,
                                },
                                {
                                    label: 'Homework Tracking',
                                    value: 91,
                                },
                            ].map((item) => (
                                <div key={item.label} className="space-y-2">
                                    <div className="flex items-center justify-between text-sm">
                                        <span>{item.label}</span>
                                        <span className="font-semibold">{item.value}%</span>
                                    </div>

                                    <div className="h-3 overflow-hidden rounded-full bg-muted">
                                        <motion.div
                                            initial={{ width: 0 }}
                                            animate={{ width: `${item.value}%` }}
                                            transition={{ duration: 0.8 }}
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
                                <BookOpen className="h-5 w-5" />
                                Subjects Analytics
                            </CardTitle>
                        </CardHeader>

                        <CardContent className="space-y-4">
                            {[
                                'Mathematics',
                                'Science',
                                'English',
                                'Geography',
                                'History',
                            ].map((subject) => (
                                <div
                                    key={subject}
                                    className="flex items-center justify-between rounded-2xl border p-4"
                                >
                                    <span className="font-medium">{subject}</span>

                                    <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                    Active
                  </span>
                                </div>
                            ))}
                        </CardContent>
                    </Card>

                    <Card className="rounded-3xl border-0 shadow-sm">
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2 text-lg">
                                <Activity className="h-5 w-5" />
                                School Insights
                            </CardTitle>
                        </CardHeader>

                        <CardContent className="space-y-4">
                            {[
                                {
                                    title: 'Teacher Motivation',
                                    value: 'High',
                                },
                                {
                                    title: 'Student Engagement',
                                    value: 'Excellent',
                                },
                                {
                                    title: 'Curriculum Progress',
                                    value: '92%',
                                },
                                {
                                    title: 'Staff Collaboration',
                                    value: 'Strong',
                                },
                            ].map((item) => (
                                <div
                                    key={item.title}
                                    className="flex items-center justify-between rounded-2xl border p-4"
                                >
                                    <span className="text-sm font-medium">{item.title}</span>

                                    <span className="font-semibold text-primary">
                    {item.value}
                  </span>
                                </div>
                            ))}
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
}