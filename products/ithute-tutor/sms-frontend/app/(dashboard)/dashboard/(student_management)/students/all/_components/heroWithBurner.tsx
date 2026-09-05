import { Badge } from "@/components/ui/badge"
import {
    GraduationCap,
    Users,
} from "lucide-react"

import { StudentRead } from "@/types/student"
import { ClassResponse } from "@/types/classes"

import * as React from "react"

import { StudentRegisterDialog } from "@/app/(dashboard)/dashboard/_components/_person/register_student"

import { Button } from "@/components/ui/button"

export function HeroWithBurner({
                                   filtered,
                                   classes,
                               }: {
    filtered: StudentRead[]
    classes: ClassResponse[]
}) {
    return (
        <div
            className="
                relative
                overflow-hidden
                border-b
                p-6
            "
        >

            {/* ================= BACKGROUND IMAGE ================= */}

            <div
                className="
                    absolute
                    inset-0
                    bg-cover
                    bg-center
                    opacity-15
                    pointer-events-none
                "
                style={{
                    backgroundImage: `url(/burner.png)`,
                }}
            />

            {/* ================= DARK GRADIENT ================= */}

            <div
                className="
                    absolute
                    inset-0
                    bg-linear-to-r
                    from-background
                    via-background/92
                    to-background/75
                "
            />

            {/* ================= GLOW ================= */}

            <div
                className="
                    absolute
                    -top-24
                    right-0
                    h-72
                    w-72
                    rounded-full
                    bg-primary/10
                    blur-3xl
                "
            />

            {/* ================= CONTENT ================= */}

            <div
                className="
                    relative
                    flex
                    flex-col
                    gap-6
                    lg:flex-row
                    lg:items-center
                    lg:justify-between
                "
            >

                {/* ================= LEFT ================= */}

                <div className="space-y-4">

                    {/* BADGE */}

                    <Badge
                        className="
                            rounded-full
                            border-0
                            bg-primary/10
                            px-4
                            py-1.5
                            text-xs
                            font-medium
                            text-primary
                            backdrop-blur
                        "
                    >
                        Student Management
                    </Badge>

                    {/* TITLE */}

                    <div className="space-y-2">

                        <h1
                            className="
                                text-3xl
                                font-black
                                tracking-tight
                                sm:text-4xl
                            "
                        >
                            Students Directory
                        </h1>

                        <p
                            className="
                                max-w-2xl
                                text-sm
                                leading-relaxed
                                text-muted-foreground
                                sm:text-base
                            "
                        >
                            Manage student records, monitor enrollment,
                            track class distribution, and quickly search
                            through academic data across your institution.
                        </p>
                    </div>
                </div>

                {/* ================= ANALYTICS ================= */}

                <div
                    className="
                        grid
                        grid-cols-1
                        gap-3
                        sm:grid-cols-2
                    "
                >

                    {/* ================= TOTAL STUDENTS ================= */}

                    <div
                        className="
                            group
                            relative
                            overflow-hidden
                            rounded-3xl
                            border
                            bg-background/70
                            px-5
                            py-4
                            shadow-lg
                            backdrop-blur-xl
                            transition-all
                            hover:-translate-y-1
                            hover:shadow-xl
                        "
                    >

                        {/* GLOW */}

                        <div
                            className="
                                absolute
                                inset-0
                                bg-linear-to-br
                                from-primary/5
                                via-transparent
                                to-transparent
                            "
                        />

                        <div className="relative flex items-center gap-4">

                            {/* ADD STUDENT BUTTON */}

                            <StudentRegisterDialog
                                button={
                                    <Button
                                        className="
                                            group
                                            h-14
                                            rounded-2xl
                                            px-4
                                            shadow-sm
                                            transition-all
                                            hover:-translate-y-0.5
                                            hover:shadow-lg
                                        "
                                    >
                                        <div
                                            className="
                                                flex
                                                h-9
                                                w-9
                                                items-center
                                                justify-center
                                                rounded-xl
                                                bg-background/20
                                                transition-transform
                                                group-hover:scale-105
                                            "
                                        >
                                            <Users className="h-4 w-4" />
                                        </div>

                                        <div
                                            className="
                                                ml-3
                                                flex
                                                flex-col
                                                items-start
                                                leading-none
                                            "
                                        >
                                            <span
                                                className="
                                                    text-sm
                                                    font-semibold
                                                "
                                            >
                                                Add Student
                                            </span>

                                            <span
                                                className="
                                                    text-[10px]
                                                    opacity-80
                                                "
                                            >
                                                Register learner
                                            </span>
                                        </div>
                                    </Button>
                                }
                            />

                            {/* STATS */}

                            <div className="space-y-1">

                                <p
                                    className="
                                        text-xs
                                        font-medium
                                        uppercase
                                        tracking-wide
                                        text-muted-foreground
                                    "
                                >
                                    Total Students
                                </p>

                                <div
                                    className="
                                        flex
                                        items-center
                                        gap-2
                                    "
                                >

                                    <h3
                                        className="
                                            text-2xl
                                            font-black
                                            tracking-tight
                                        "
                                    >
                                        {filtered.length}
                                    </h3>

                                    <Badge
                                        variant="secondary"
                                        className="
                                            rounded-full
                                            px-2.5
                                            py-1
                                            text-[10px]
                                            font-semibold
                                        "
                                    >
                                        Active
                                    </Badge>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* ================= TOTAL CLASSES ================= */}

                    <div
                        className="
                            group
                            relative
                            overflow-hidden
                            rounded-3xl
                            border
                            bg-background/70
                            px-5
                            py-4
                            shadow-lg
                            backdrop-blur-xl
                            transition-all
                            hover:-translate-y-1
                            hover:shadow-xl
                        "
                    >

                        {/* GLOW */}

                        <div
                            className="
                                absolute
                                inset-0
                                bg-linear-to-br
                                from-primary/5
                                via-transparent
                                to-transparent
                            "
                        />

                        <div className="relative flex items-center gap-4">

                            {/* ICON */}

                            <div
                                className="
                                    flex
                                    h-14
                                    w-14
                                    items-center
                                    justify-center
                                    rounded-2xl
                                    bg-primary/10
                                    ring-1
                                    ring-primary/10
                                "
                            >
                                <GraduationCap className="h-6 w-6 text-primary" />
                            </div>

                            {/* TEXT */}

                            <div className="space-y-1">

                                <p
                                    className="
                                        text-xs
                                        font-medium
                                        uppercase
                                        tracking-wide
                                        text-muted-foreground
                                    "
                                >
                                    Active Classes
                                </p>

                                <h3
                                    className="
                                        text-2xl
                                        font-black
                                        tracking-tight
                                    "
                                >
                                    {classes.length}
                                </h3>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}