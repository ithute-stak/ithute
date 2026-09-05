// app/(dashboard)/dashboard/(student_management)/students/all/page.tsx

'use client'

import * as React from 'react'

import {
    Search,
    Users,
    GraduationCap,
    ChevronLeft,
    ChevronRight,
} from 'lucide-react'

import {Input} from '@/components/ui/input'
import {Card} from '@/components/ui/card'
import {Badge} from '@/components/ui/badge'
import {Button} from '@/components/ui/button'

import {useStudentFilters} from '@/store/hooks/useStudentFilters'
import {useAppData} from '@/provider/dataProvider'

import {AllStudentTable} from '@/app/(dashboard)/dashboard/(student_management)/students/all/_components/data-table'
import {HeroWithBurner} from "@/app/(dashboard)/dashboard/(student_management)/students/all/_components/heroWithBurner";

export default function StudentsTable() {
    const {
        students,
        classes,
    } = useAppData()

    const {
        search,
        setSearch,

        classId,
        setClassId,

        gender,
        setGender,

        nationality,
        setNationality,

        nationalities,

        filtered,
        paginatedStudents,

        page,
        setPage,

        totalPages,
    } = useStudentFilters(students)

    return (
        <Card
            className="
                flex
                h-[calc(100vh-7rem)]
                flex-col
                overflow-hidden
                rounded-4xl
                border-0
                bg-background
                shadow-xl
            "
        >

            {/* ================= HERO ================= */}

            <HeroWithBurner filtered={filtered} classes={classes}/>
            {/* ================= FILTERS ================= */}

            <div
                className="
                    flex
                    flex-col
                    gap-4
                    border-b
                    bg-muted/20
                    p-5
                    md:flex-row
                    md:items-center
                    md:justify-between
                "
            >

                {/* SEARCH */}
                <div className="relative w-full md:max-w-md">

                    <Search
                        className="
                            absolute
                            left-4
                            top-3.5
                            h-4
                            w-4
                            text-muted-foreground
                        "
                    />

                    <Input
                        placeholder="
                            Search by student name
                            or admission number...
                        "
                        value={search}
                        onChange={(e) =>
                            setSearch(
                                e.target.value
                            )
                        }
                        className="
                            h-12
                            rounded-2xl
                            border-0
                            bg-background
                            pl-11
                            shadow-sm
                        "
                    />
                </div>

                {/* CLASS FILTER */}
                <div className="flex items-center gap-3">

                    <select
                        className="
        h-12
        rounded-2xl
        border-0
        bg-background
        px-4
        shadow-sm
        outline-none
    "
                        value={gender}
                        onChange={(e) =>
                            setGender(e.target.value)
                        }
                    >
                        <option value="all">
                            All Genders
                        </option>

                        <option value="male">
                            Male
                        </option>

                        <option value="female">
                            Female
                        </option>
                    </select>

                    <select className=" h-12 rounded-2xl border-0 bg-background px-4 shadow-sm outline-none"
                        value={nationality}
                        onChange={(e) =>
                            setNationality(
                                e.target.value
                            )
                        }
                    >
                        <option value="all">
                            All Nationalities
                        </option>

                        {nationalities.map((item) => (
                            <option
                                key={item}
                                value={item}
                            >
                                {item}
                            </option>
                        ))}
                    </select>

                    <select
                        className="
                            h-12
                            rounded-2xl
                            border-0
                            bg-background
                            px-4
                            shadow-sm
                            outline-none
                        "
                        value={classId}
                        onChange={(e) =>
                            setClassId(
                                e.target.value
                            )
                        }
                    >
                        <option value="all">
                            All Classes
                        </option>

                        {classes.map((c) => (
                            <option
                                key={c.id}
                                value={c.id}
                            >
                                {c.name}
                            </option>
                        ))}
                    </select>

                    <Badge
                        variant="secondary"
                        className="
                            rounded-full
                            px-4
                            py-2
                            text-xs
                        "
                    >
                        Showing{' '}
                        {
                            paginatedStudents.length
                        }{' '}
                        of {filtered.length}
                    </Badge>
                </div>
            </div>

            {/* ================= TABLE ================= */}

            <div
                className="
                    flex-1
                    overflow-hidden
                    p-5
                "
            >
                <div
                    className="
                        h-full
                        overflow-auto
                        rounded-3xl
                        border
                        bg-background
                        shadow-sm p-8
                    "
                >
                    <AllStudentTable
                        filtered={
                            paginatedStudents
                        }
                        classes={classes}
                    />
                </div>
            </div>

            {/* ================= PAGINATION ================= */}

            <div
                className="
                    flex
                    items-center
                    justify-between
                    border-t
                    bg-muted/20
                    px-6
                    py-4
                "
            >

                <p
                    className="
                        text-sm
                        text-muted-foreground
                    "
                >
                    Page {page} of{' '}
                    {totalPages}
                </p>

                <div className="flex items-center gap-2">

                    <Button
                        variant="outline"
                        size="sm"
                        disabled={page <= 1}
                        onClick={() =>
                            setPage(
                                (prev) =>
                                    prev - 1
                            )
                        }
                        className="rounded-xl"
                    >
                        <ChevronLeft className="mr-1 h-4 w-4"/>
                        Previous
                    </Button>

                    <Button
                        size="sm"
                        disabled={
                            page >= totalPages
                        }
                        onClick={() =>
                            setPage(
                                (prev) =>
                                    prev + 1
                            )
                        }
                        className="rounded-xl"
                    >
                        Next
                        <ChevronRight className="ml-1 h-4 w-4"/>
                    </Button>
                </div>
            </div>
        </Card>
    )
}