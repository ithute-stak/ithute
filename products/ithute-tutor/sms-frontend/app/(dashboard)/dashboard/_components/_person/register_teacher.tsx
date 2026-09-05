"use client"

import * as React from "react"
import { useAppDispatch, useAppSelector } from "@/store/hooks"
import { toast } from "sonner"

import {
    Dialog,
    DialogContent,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog"

import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"

import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
} from "@/components/ui/command"

import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover"

import { Check, ChevronsUpDown, Plus } from "lucide-react"
import { cn } from "@/lib/utils"

import { TeacherCreate } from "@/types/teacher"
import { createTeacherThunk } from "@/store/features/thunks/teacherThunks"
import { GenderEnum, UserRole } from "@/types/shared.primitive"

export function TeacherRegisterDialog() {
    const dispatch = useAppDispatch()
    const { loading } = useAppSelector((state) => state.teacher)
    const { schools } = useAppSelector((state) => state.schools)

    const [open, setOpen] = React.useState(false)
    const [schoolOpen, setSchoolOpen] = React.useState(false)

    const teacherForm = React.useCallback((): TeacherCreate => ({
        school_id: "",
        user: {
            username: "",
            email: "",
            password: "",
            role: UserRole.teacher,
            school_id: "",
            person: {
                first_name: "",
                last_name: "",
                gender: GenderEnum.female,
                date_of_birth: "",
                nationality: "",
                national_id: "",
            },
        },
    }), [])

    const [form, setForm] = React.useState<TeacherCreate>(teacherForm)

    /* =========================
       SAFE UPDATERS
    ========================= */
    const setTeacher = <K extends keyof TeacherCreate>(
        key: K,
        value: TeacherCreate[K]
    ) => {
        setForm((prev) => ({ ...prev, [key]: value }))
    }

    const setUser = <K extends keyof TeacherCreate["user"]>(
        key: K,
        value: TeacherCreate["user"][K]
    ) => {
        setForm((prev) => ({
            ...prev,
            user: { ...prev.user, [key]: value },
        }))
    }

    const setPerson = <K extends keyof TeacherCreate["user"]["person"]>(
        key: K,
        value: TeacherCreate["user"]["person"][K]
    ) => {
        setForm((prev) => ({
            ...prev,
            user: {
                ...prev.user,
                person: { ...prev.user.person, [key]: value },
            },
        }))
    }

    const selectedSchool = schools.find((s) => s.id === form.school_id)

    /* =========================
       SUBMIT
    ========================= */
    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()

        const res = await dispatch(createTeacherThunk(form))

        if (createTeacherThunk.fulfilled.match(res)) {
            toast.success("Teacher created successfully")
            setOpen(false)
        } else {
            toast.error("Failed to create teacher")
        }
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button className="rounded-xl px-5">
                    <Plus className="size-4" />
                </Button>
            </DialogTrigger>

            <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-y-auto rounded-2xl">
                <DialogHeader>
                    <DialogTitle className="text-xl font-semibold">
                        Teacher Registration
                    </DialogTitle>
                </DialogHeader>

                <form onSubmit={handleSubmit} className="space-y-8">

                    {/* ================= SCHOOL ================= */}
                    <div className="space-y-2">
                        <Label>School</Label>

                        <Popover open={schoolOpen} onOpenChange={setSchoolOpen}>
                            <PopoverTrigger asChild>
                                <Button
                                    variant="outline"
                                    role="combobox"
                                    className="w-full justify-between"
                                >
                                    {selectedSchool
                                        ? selectedSchool.name
                                        : "Select school"}
                                    <ChevronsUpDown className="ml-2 h-4 w-4 opacity-50" />
                                </Button>
                            </PopoverTrigger>

                            <PopoverContent className="w-full p-0">
                                <Command>
                                    <CommandInput placeholder="Search school..." />
                                    <CommandList>
                                        <CommandEmpty>No school found.</CommandEmpty>
                                        <CommandGroup>
                                            {schools.map((school) => (
                                                <CommandItem
                                                    key={school.id}
                                                    value={school.name}
                                                    onSelect={() => {
                                                        setTeacher("school_id", school.id)
                                                        setUser("school_id", school.id)
                                                        setSchoolOpen(false)
                                                    }}
                                                >
                                                    <Check
                                                        className={cn(
                                                            "mr-2 h-4 w-4",
                                                            form.school_id === school.id
                                                                ? "opacity-100"
                                                                : "opacity-0"
                                                        )}
                                                    />
                                                    {school.name}
                                                </CommandItem>
                                            ))}
                                        </CommandGroup>
                                    </CommandList>
                                </Command>
                            </PopoverContent>
                        </Popover>
                    </div>

                    {/* ================= USER INFO ================= */}
                    <div className="space-y-4">
                        <h3 className="font-medium text-sm text-muted-foreground">
                            Account Details
                        </h3>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1">
                                <Label>Username</Label>
                                <Input
                                    value={form.user.username}
                                    onChange={(e) =>
                                        setUser("username", e.target.value)
                                    }
                                />
                            </div>

                            <div className="space-y-1">
                                <Label>Email</Label>
                                <Input
                                    value={form.user.email}
                                    onChange={(e) =>
                                        setUser("email", e.target.value)
                                    }
                                />
                            </div>

                            <div className="col-span-2 space-y-1">
                                <Label>Password</Label>
                                <Input
                                    type="password"
                                    value={form.user.password}
                                    onChange={(e) =>
                                        setUser("password", e.target.value)
                                    }
                                />
                            </div>
                        </div>
                    </div>

                    {/* ================= PERSON INFO ================= */}
                    <div className="space-y-4">
                        <h3 className="font-medium text-sm text-muted-foreground">
                            Personal Details
                        </h3>

                        <div className="grid grid-cols-2 gap-4">

                            <div className="space-y-1">
                                <Label>First Name</Label>
                                <Input
                                    value={form.user.person.first_name}
                                    onChange={(e) =>
                                        setPerson("first_name", e.target.value)
                                    }
                                />
                            </div>

                            <div className="space-y-1">
                                <Label>Last Name</Label>
                                <Input
                                    value={form.user.person.last_name}
                                    onChange={(e) =>
                                        setPerson("last_name", e.target.value)
                                    }
                                />
                            </div>

                            <div className="space-y-1">
                                <Label>Date of Birth</Label>
                                <Input
                                    type="date"
                                    value={form.user.person.date_of_birth}
                                    onChange={(e) =>
                                        setPerson("date_of_birth", e.target.value)
                                    }
                                />
                            </div>

                            <div className="space-y-1">
                                <Label>Nationality</Label>
                                <Input
                                    value={form.user.person.nationality}
                                    onChange={(e) =>
                                        setPerson("nationality", e.target.value)
                                    }
                                />
                            </div>

                            {/* ✅ NEW FIELD */}
                            <div className="col-span-2 space-y-1">
                                <Label>National ID</Label>
                                <Input
                                    value={form.user.person.national_id??""}
                                    onChange={(e) =>
                                        setPerson("national_id", e.target.value)
                                    }
                                    placeholder="e.g. 123456789"
                                />
                            </div>
                        </div>
                    </div>

                    {/* ================= SUBMIT ================= */}
                    <DialogFooter>
                        <Button
                            type="submit"
                            disabled={loading}
                            className="w-full rounded-xl"
                        >
                            {loading ? "Creating..." : "Create Teacher"}
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    )
}