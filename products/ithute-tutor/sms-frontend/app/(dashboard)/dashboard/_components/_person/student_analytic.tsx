"use client"

import * as React from "react"

import {Card, CardContent, CardHeader, CardTitle,} from "@/components/ui/card"

import {Badge} from "@/components/ui/badge"

import {CalendarDays, Globe, Mars, Users, Venus,} from "lucide-react"

import {Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip,} from "recharts"

import {StudentRead} from "@/types/student"
import {UserRole} from "@/types/shared.primitive";
import {useAppData} from "@/provider/dataProvider";

type Props = {
    students: StudentRead[]
}

export default function StudentAnalytics() {

    /* ================= TOTAL ================= */
    const {
        students,
    } = useAppData()

    const data = students.filter((q)=>q.user.role ===UserRole.student)

    const totaldata = data.length

    /* ================= GENDER ================= */

    const maledata = data.filter(
        (s) => s.user?.person?.gender === "male"
    ).length

    const femaledata = data.filter(
        (s) => s.user?.person?.gender === "female"
    ).length

    const malePercentage =
        totaldata > 0 ? (maledata / totaldata) * 100 : 0

    const femalePercentage =
        totaldata > 0 ? (femaledata / totaldata) * 100 : 0

    const genderData = [
        { name: "Male", value: maledata },
        { name: "Female", value: femaledata },
    ]

    /* ================= NATIONALITIES ================= */

    const nationalityMap = data.reduce((acc: Record<string, number>, s) => {
        const n = s.user?.person?.nationality || "Unknown"
        acc[n] = (acc[n] || 0) + 1
        return acc
    }, {})

    const nationalities = Object.entries(nationalityMap)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 6)

    /* ================= AGE ================= */

    const calculateAge = (dob?: string) => {
        if (!dob) return 0

        const birth = new Date(dob)
        const today = new Date()

        let age = today.getFullYear() - birth.getFullYear()

        const m = today.getMonth() - birth.getMonth()

        if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) {
            age--
        }

        return age
    }

    const ages = data
        .map((s) => calculateAge(s.user?.person?.date_of_birth))
        .filter((a) => a > 0)

    const averageAge =
        ages.length > 0
            ? (ages.reduce((a, b) => a + b, 0) / ages.length).toFixed(1)
            : "0"

    /* ================= UI ================= */

    return (
        <div className="space-y-4 w-full min-w-0">

            {/* ================= HEADER CARD ================= */}
            <Card className="border-muted shadow-sm">
                <CardHeader className="flex flex-row items-center justify-between space-y-0">
                    <div className="space-y-1">
                        <CardTitle className="text-sm font-medium text-muted-foreground">
                            Total data
                        </CardTitle>

                        <div className="text-2xl font-bold">
                            {totaldata}
                        </div>
                    </div>

                    <div className="flex items-center gap-2">
                        <Badge className="gap-1">
                            <Users className="h-3 w-3" />
                            Active
                        </Badge>
                    </div>
                </CardHeader>
            </Card>

            {/* ================= GENDER PIE ================= */}
            <Card className="shadow-sm border-muted">
                <CardHeader>
                    <CardTitle className="text-sm font-medium">
                        Gender Distribution
                    </CardTitle>
                </CardHeader>

                <CardContent>
                    {/* IMPORTANT FIX: proper height */}
                    <div className="w-full h-[260px] min-h-[260px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie
                                    data={genderData}
                                    cx="50%"
                                    cy="50%"
                                    outerRadius={90}
                                    dataKey="value"
                                    label
                                >
                                    <Cell fill="#3b82f6" />
                                    <Cell fill="#ec4899" />
                                </Pie>

                                <Tooltip />
                                <Legend />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>

                    {/* breakdown */}
                    <div className="mt-5 space-y-3">

                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-sm">
                                <Mars className="h-4 w-4 text-blue-500" />
                                Male
                            </div>

                            <Badge variant="outline">
                                {maledata} ({malePercentage.toFixed(1)}%)
                            </Badge>
                        </div>

                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-sm">
                                <Venus className="h-4 w-4 text-pink-500" />
                                Female
                            </div>

                            <Badge variant="outline">
                                {femaledata} ({femalePercentage.toFixed(1)}%)
                            </Badge>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* ================= AGE ================= */}
            <Card className="shadow-sm border-muted">
                <CardHeader>
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <CalendarDays className="h-4 w-4" />
                        Age Analytics
                    </CardTitle>
                </CardHeader>

                <CardContent>
                    <div className="text-3xl font-bold">
                        {averageAge}
                    </div>

                    <p className="text-xs text-muted-foreground mt-1">
                        Average student age
                    </p>
                </CardContent>
            </Card>

            {/* ================= NATIONALITIES ================= */}
            <Card className="shadow-sm border-muted">
                <CardHeader>
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <Globe className="h-4 w-4" />
                        Nationalities
                    </CardTitle>
                </CardHeader>

                <CardContent className="space-y-3">
                    {nationalities.length > 0 ? (
                        nationalities.map(([nation, count]) => (
                            <div
                                key={nation}
                                className="flex items-center justify-between"
                            >
                                <span className="text-sm truncate">
                                    {nation}
                                </span>

                                <Badge variant="secondary">
                                    {count}
                                </Badge>
                            </div>
                        ))
                    ) : (
                        <p className="text-sm text-muted-foreground">
                            No nationality data
                        </p>
                    )}
                </CardContent>
            </Card>

        </div>
    )
}