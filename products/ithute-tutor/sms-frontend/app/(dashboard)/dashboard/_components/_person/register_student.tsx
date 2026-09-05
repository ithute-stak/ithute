"use client"

import * as React from "react"
import { format } from "date-fns"

import { useAppDispatch, useAppSelector } from "@/store/hooks"

import { toast } from "sonner"

import {
    Dialog,
    DialogContent,
    DialogFooter,
    DialogTrigger,
} from "@/components/ui/dialog"

import { Input } from "@/components/ui/input"

import { Label } from "@/components/ui/label"

import { Button } from "@/components/ui/button"

import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover"


import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"

import { Calendar } from "@/components/ui/calendar"

import {Plus, UsersIcon} from "lucide-react"

import { StudentCreate } from "@/types/student"

import { createStudentThunk } from "@/store/features/thunks/studentThunks"

import {
    GenderEnum,
    UserRole,
} from "@/types/shared.primitive"

import { generateAdmissionNumber } from "@/lib/admition_number"
import {DialogHeroHeader} from "@/components/customUI/dialogHeader";
import {SchoolSelectPopover} from "@/components/customUI/schoolSelectPopover";
import {ClassSelectPopover} from "@/components/customUI/classSelectPopover";

/* ================= TYPES ================= */

type ClassType = {
    id: string
    name: string
}


type StudentFormUser =
    StudentCreate["user"]

type StudentFormPerson =
    StudentCreate["user"]["person"]

/* ================= CLEANER ================= */

function cleanPayload<T>(obj: T): T {
    if (
        obj === null ||
        obj === undefined
    ) {
        return obj
    }

    if (typeof obj === "string") {
        const trimmed = obj.trim()

        return (
            trimmed === ""
                ? undefined
                : trimmed
        ) as T
    }

    if (Array.isArray(obj)) {
        return obj
            .map(cleanPayload)
            .filter(Boolean) as T
    }

    if (typeof obj === "object") {
        const result: Record<
            string,
            unknown
        > = {}

        Object.entries(
            obj as Record<
                string,
                unknown
            >
        ).forEach(([key, value]) => {
            const cleaned =
                cleanPayload(value)

            if (
                cleaned !== undefined &&
                cleaned !== null &&
                cleaned !== ""
            ) {
                result[key] = cleaned
            }
        })

        return result as T
    }

    return obj
}

/* ================= COMPONENT ================= */

interface props {
    button?:React.ReactNode
}

export function StudentRegisterDialog({button}:props) {
    const dispatch = useAppDispatch()

    const {
        loading,
        students,
    } = useAppSelector(
        (state) => state.students
    )

    const classes =
        useAppSelector(
            (state) =>
                state.class.classes
        ) as ClassType[]


    /* ================= UI STATE ================= */

    const [open, setOpen] =
        React.useState(false)

    const [dobOpen, setDobOpen] =
        React.useState(false)

    /* ================= INITIAL FORM ================= */

    const createInitialForm =
        React.useCallback(
            (): StudentCreate => ({
                admission_number:
                    generateAdmissionNumber(
                        students
                    ),

                class_id: "",

                user: {
                    username: "",
                    email: "",
                    password: "",

                    role:
                    UserRole.student,

                    school_id: "",

                    person: {
                        first_name: "",
                        last_name: "",

                        gender:
                        GenderEnum.male,

                        date_of_birth:
                            "",

                        nationality:
                            "",

                        national_id:
                            "",
                    },
                },
            }),
            [students]
        )

    const [form, setForm] =
        React.useState<StudentCreate>(
            createInitialForm()
        )

    /* ================= SETTERS ================= */

    const setField = <
        K extends keyof StudentCreate
    >(
        key: K,
        value: StudentCreate[K]
    ) => {
        setForm((prev) => ({
            ...prev,
            [key]: value,
        }))
    }

    const setUserField = <
        K extends keyof StudentFormUser
    >(
        key: K,
        value: StudentFormUser[K]
    ) => {
        setForm((prev) => ({
            ...prev,

            user: {
                ...prev.user,
                [key]: value,
            },
        }))
    }

    const setPersonField = <
        K extends keyof StudentFormPerson
    >(
        key: K,
        value: StudentFormPerson[K]
    ) => {
        setForm((prev) => ({
            ...prev,

            user: {
                ...prev.user,

                person: {
                    ...prev.user.person,
                    [key]: value,
                },
            },
        }))
    }

    /* ================= SUBMIT ================= */

    const handleSubmit = async (
        e: React.FormEvent<HTMLFormElement>
    ) => {
        e.preventDefault()

        const payload =
            cleanPayload(form)

        const res = await dispatch(
            createStudentThunk(payload)
        )

        if (
            createStudentThunk.fulfilled.match(
                res
            )
        ) {
            toast.success(
                "Student created successfully"
            )

            setForm(
                createInitialForm()
            )

            setOpen(false)
        } else {
            toast.error(
                "Failed to create student"
            )
        }
    }

    /* ================= UI ================= */

    return (
        <Dialog
            open={open}
            onOpenChange={(
                value
            ) => {
                setOpen(value)

                if (value) {
                    setForm(
                        createInitialForm()
                    )
                }
            }}
        >
            {/* TRIGGER */}
            <DialogTrigger asChild>
                {button?button:<Button className="gap-2 rounded-xl shadow-sm">
                    <Plus className="size-4" />
                </Button>}
            </DialogTrigger>

            {/* DIALOG */}
            <DialogContent className=" overflow-hidden rounded-4xl border-0 p-0 sm:max-w-3xl">
                <DialogHeroHeader
                    title="Student Registration"
                    description="Fill in the student
                        details below."
                    icon={<UsersIcon className="h-8 w-8" />}
                />

                <div className="space-y-8 px-8 pb-8">
                    <form
                        onSubmit={
                            handleSubmit
                        }
                        className="mt-6 space-y-8"
                    >
                        {/* SCHOOL + CLASS */}
                        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                            {/* SCHOOL */}
                            <SchoolSelectPopover
                                id={form.user.school_id??""}
                                setId={(schoolId: string) =>
                                    setUserField("school_id", schoolId)
                                }
                            />

                            {/* CLASS */}
                            <ClassSelectPopover
                                value={form.class_id??""}
                                onChange={(value) =>
                                    setField('class_id', value)
                                }
                                classes={classes}
                            />
                        </div>

                        {/* ACCOUNT */}
                        <div className="space-y-4">
                            <div className="text-sm font-medium text-muted-foreground">
                                Account
                                Information
                            </div>

                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <Input
                                    placeholder="Username"
                                    value={
                                        form.user
                                            .username
                                    }
                                    onChange={(
                                        e
                                    ) =>
                                        setUserField(
                                            "username",
                                            e.target
                                                .value
                                        )
                                    }
                                />

                                <Input
                                    placeholder="Email"
                                    type="email"
                                    value={
                                        form.user
                                            .email
                                    }
                                    onChange={(
                                        e
                                    ) =>
                                        setUserField(
                                            "email",
                                            e.target
                                                .value
                                        )
                                    }
                                />
                            </div>

                            <Input
                                type="password"
                                placeholder="Password"
                                value={
                                    form.user
                                        .password
                                }
                                onChange={(
                                    e
                                ) =>
                                    setUserField(
                                        "password",
                                        e.target
                                            .value
                                    )
                                }
                            />
                        </div>

                        {/* PERSONAL */}
                        <div className="space-y-4">
                            <div className="text-sm font-medium text-muted-foreground">
                                Personal
                                Information
                            </div>

                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <Input
                                    placeholder="First Name"
                                    value={
                                        form.user
                                            .person
                                            .first_name
                                    }
                                    onChange={(
                                        e
                                    ) =>
                                        setPersonField(
                                            "first_name",
                                            e.target
                                                .value
                                        )
                                    }
                                />

                                <Input
                                    placeholder="Last Name"
                                    value={
                                        form.user
                                            .person
                                            .last_name
                                    }
                                    onChange={(
                                        e
                                    ) =>
                                        setPersonField(
                                            "last_name",
                                            e.target
                                                .value
                                        )
                                    }
                                />
                            </div>

                            {/* GENDER */}
                            <Select
                                value={
                                    form.user
                                        .person
                                        .gender
                                }
                                onValueChange={(
                                    value: GenderEnum
                                ) =>
                                    setPersonField(
                                        "gender",
                                        value
                                    )
                                }
                            >
                                <SelectTrigger>
                                    <SelectValue placeholder="Select gender" />
                                </SelectTrigger>

                                <SelectContent>
                                    <SelectItem
                                        value={
                                            GenderEnum.male
                                        }
                                    >
                                        Male
                                    </SelectItem>

                                    <SelectItem
                                        value={
                                            GenderEnum.female
                                        }
                                    >
                                        Female
                                    </SelectItem>
                                </SelectContent>
                            </Select>

                            {/* DOB */}
                            <Popover
                                open={dobOpen}
                                onOpenChange={
                                    setDobOpen
                                }
                            >
                                <PopoverTrigger asChild>
                                    <Button
                                        variant="outline"
                                        className="w-full justify-start"
                                    >
                                        {form
                                            .user
                                            .person
                                            .date_of_birth
                                            ? format(
                                                new Date(
                                                    form.user.person.date_of_birth
                                                ),
                                                "PPP"
                                            )
                                            : "Select date of birth"}
                                    </Button>
                                </PopoverTrigger>

                                <PopoverContent>
                                    <Calendar
                                        mode="single"
                                        selected={
                                            form
                                                .user
                                                .person
                                                .date_of_birth
                                                ? new Date(
                                                    form.user.person.date_of_birth
                                                )
                                                : undefined
                                        }
                                        onSelect={(
                                            date
                                        ) => {
                                            if (
                                                !date
                                            ) {
                                                return
                                            }

                                            setPersonField(
                                                "date_of_birth",
                                                format(
                                                    date,
                                                    "yyyy-MM-dd"
                                                )
                                            )

                                            setDobOpen(
                                                false
                                            )
                                        }}
                                    />
                                </PopoverContent>
                            </Popover>

                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <Input
                                    placeholder="Nationality"
                                    value={
                                        form.user
                                            .person
                                            .nationality ??
                                        ""
                                    }
                                    onChange={(
                                        e
                                    ) =>
                                        setPersonField(
                                            "nationality",
                                            e.target
                                                .value
                                        )
                                    }
                                />

                                <Input
                                    placeholder="National ID"
                                    value={
                                        form.user
                                            .person
                                            .national_id ??
                                        ""
                                    }
                                    onChange={(
                                        e
                                    ) =>
                                        setPersonField(
                                            "national_id",
                                            e.target
                                                .value
                                        )
                                    }
                                />
                            </div>
                        </div>

                        {/* ADMISSION */}
                        <div className="rounded-2xl border bg-muted/40 p-4">
                            <Label className="text-xs text-muted-foreground">
                                Admission
                                Number
                            </Label>

                            <div className="mt-1 text-lg font-semibold tracking-wide">
                                {
                                    form.admission_number
                                }
                            </div>
                        </div>

                        {/* SUBMIT */}
                        <DialogFooter>
                            <Button
                                type="submit"
                                disabled={
                                    loading
                                }
                                className="w-full rounded-xl"
                            >
                                {loading
                                    ? "Creating student..."
                                    : "Create Student"}
                            </Button>
                        </DialogFooter>
                    </form>
                </div>
            </DialogContent>
        </Dialog>
    )
}