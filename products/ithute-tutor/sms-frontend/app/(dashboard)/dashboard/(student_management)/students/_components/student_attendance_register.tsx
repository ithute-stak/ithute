'use client'

import * as React from 'react'

import { useMemo, useState } from 'react'

import { format } from 'date-fns'

import {
    CalendarIcon,
    CheckCircle2,
    Clock3,
    Loader2,
    Plus,
    UserRound,
    XCircle,
} from 'lucide-react'

import { motion, AnimatePresence } from 'framer-motion'

import { Button } from '@/components/ui/button'

import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog'

import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'

import { Label } from '@/components/ui/label'

import { Textarea } from '@/components/ui/textarea'

import { Calendar } from '@/components/ui/calendar'

import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from '@/components/ui/popover'

import {
    Card,
    CardContent,
} from '@/components/ui/card'

import {
    Avatar,
    AvatarFallback,
} from '@/components/ui/avatar'

import { Badge } from '@/components/ui/badge'

import { Separator } from '@/components/ui/separator'

import { cn } from '@/lib/utils'

import { createStudentAttendance } from '@/api/person/student/attendance/actions'

import { useAppData } from '@/provider/dataProvider'

export default function StudentAttendanceDialog() {
    const { students } = useAppData()
    const {
        classes,
    } = useAppData()
    const [open, setOpen] = useState(false)

    const [loading, setLoading] = useState(false)

    const [date, setDate] = useState<Date>(
        new Date()
    )

    const [form, setForm] = useState({
        student_id: '',
        status: 'present',
        remarks: '',
    })

    const selectedStudent = useMemo(() => {
        return students.find(
            (student) =>
                student.id === form.student_id
        )
    }, [form.student_id, students])

    async function handleSubmit() {
        if (!form.student_id) return

        try {
            setLoading(true)

            await createStudentAttendance({
                student_id: form.student_id,

                classroom_id:
                    selectedStudent?.class_id ||
                    null,

                attendance_date: format(
                    date,
                    'yyyy-MM-dd'
                ),

                status: form.status as
                    | 'present'
                    | 'absent'
                    | 'late',

                remarks: form.remarks || null,
            })

            setOpen(false)

            setForm({
                student_id: '',
                status: 'present',
                remarks: '',
            })

            setDate(new Date())

        } catch (error) {
            console.error(
                'Failed to register attendance',
                error
            )

        } finally {
            setLoading(false)
        }
    }

    const statusConfig = {
        present: {
            icon: CheckCircle2,
            label: 'Present',
            className:
                'border-green-500/20 bg-green-500/10 text-green-600',
        },

        absent: {
            icon: XCircle,
            label: 'Absent',
            className:
                'border-red-500/20 bg-red-500/10 text-red-600',
        },

        late: {
            icon: Clock3,
            label: 'Late',
            className:
                'border-yellow-500/20 bg-yellow-500/10 text-yellow-600',
        },
    }

    const ActiveStatus =
        statusConfig[
            form.status as keyof typeof statusConfig
            ]

    return (
        <Dialog
            open={open}
            onOpenChange={setOpen}
        >
            <DialogTrigger asChild>
                <Button
                    size="lg"
                    className="rounded-2xl shadow-sm"
                >
                    <Plus className="size-4" />
                </Button>
            </DialogTrigger>

            <DialogContent className="overflow-hidden rounded-4xl border-0 p-0 shadow-2xl sm:max-w-3xl">
                {/* HEADER */}
                <div className="relative overflow-hidden bg-linear-to-br from-primary via-primary to-primary/80 px-8 py-8 text-primary-foreground">
                    <div className="absolute inset-0 opacity-10">
                        <div className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white" />

                        <div className="absolute bottom-0 left-0 h-24 w-24 rounded-full bg-white" />
                    </div>

                    <DialogHeader className="relative z-10">
                        <DialogTitle className="text-3xl font-bold">
                            Student Attendance
                        </DialogTitle>

                        <DialogDescription className="mt-2 text-primary-foreground/80">
                            Register and manage
                            daily student
                            attendance records.
                        </DialogDescription>
                    </DialogHeader>
                </div>

                {/* BODY */}
                <div className="grid gap-0 lg:grid-cols-[1fr_320px]">
                    {/* FORM */}
                    <div className="space-y-6 p-8">
                        {/* STUDENT */}
                        <div className="space-y-2">
                            <Label className="text-sm font-semibold">
                                Student
                            </Label>

                            <Select
                                value={
                                    form.student_id
                                }
                                onValueChange={(
                                    value
                                ) =>
                                    setForm(
                                        (prev) => ({
                                            ...prev,
                                            student_id:
                                            value,
                                        })
                                    )
                                }
                            >
                                <SelectTrigger className="h-13 rounded-2xl border-muted-foreground/20">
                                    <SelectValue placeholder="Select student" />
                                </SelectTrigger>

                                <SelectContent>
                                    {students.map(
                                        (
                                            student
                                        ) => (
                                            <SelectItem
                                                key={
                                                    student.id
                                                }
                                                value={
                                                    student.id
                                                }
                                            >
                                                <div className="flex items-center gap-3">
                                                    <Avatar className="h-7 w-7">
                                                        <AvatarFallback>
                                                            {student.user?.person?.first_name?.[0]}
                                                        </AvatarFallback>
                                                    </Avatar>

                                                    <span>
                                                        {
                                                            student
                                                                .user
                                                                ?.person
                                                                ?.first_name
                                                        }{' '}
                                                        {
                                                            student
                                                                .user
                                                                ?.person
                                                                ?.last_name
                                                        }
                                                    </span>
                                                </div>
                                            </SelectItem>
                                        )
                                    )}
                                </SelectContent>
                            </Select>
                        </div>

                        {/* DATE */}
                        <div className="space-y-2">
                            <Label className="text-sm font-semibold">
                                Attendance Date
                            </Label>

                            <Popover>
                                <PopoverTrigger asChild>
                                    <Button
                                        variant="outline"
                                        className={cn(
                                            'h-13 w-full justify-start rounded-2xl border-muted-foreground/20 text-left font-normal'
                                        )}
                                    >
                                        <CalendarIcon className="mr-3 h-4 w-4" />

                                        {format(
                                            date,
                                            'PPP'
                                        )}
                                    </Button>
                                </PopoverTrigger>

                                <PopoverContent
                                    className="w-auto rounded-2xl border-0 p-0 shadow-xl"
                                    align="start"
                                >
                                    <Calendar
                                        mode="single"
                                        selected={
                                            date
                                        }
                                        onSelect={(
                                            value
                                        ) => {
                                            if (
                                                value
                                            ) {
                                                setDate(
                                                    value
                                                )
                                            }
                                        }}
                                        required
                                        initialFocus
                                    />
                                </PopoverContent>
                            </Popover>
                        </div>

                        {/* STATUS */}
                        <div className="space-y-3">
                            <Label className="text-sm font-semibold">
                                Attendance
                                Status
                            </Label>

                            <div className="grid grid-cols-3 gap-3">
                                {Object.entries(
                                    statusConfig
                                ).map(
                                    ([
                                         key,
                                         value,
                                     ]) => {
                                        const Icon =
                                            value.icon

                                        const active =
                                            form.status ===
                                            key

                                        return (
                                            <motion.button
                                                whileTap={{
                                                    scale: 0.97,
                                                }}
                                                key={
                                                    key
                                                }
                                                type="button"
                                                onClick={() =>
                                                    setForm(
                                                        (
                                                            prev
                                                        ) => ({
                                                            ...prev,
                                                            status:
                                                            key,
                                                        })
                                                    )
                                                }
                                                className={cn(
                                                    'flex flex-col items-center justify-center gap-3 rounded-3xl border p-5 transition-all duration-200',
                                                    active
                                                        ? value.className
                                                        : 'border-border bg-background hover:bg-muted/50'
                                                )}
                                            >
                                                <div
                                                    className={cn(
                                                        'rounded-2xl p-3',
                                                        active
                                                            ? 'bg-white/70'
                                                            : 'bg-muted'
                                                    )}
                                                >
                                                    <Icon className="h-6 w-6" />
                                                </div>

                                                <span className="text-sm font-semibold">
                                                    {
                                                        value.label
                                                    }
                                                </span>
                                            </motion.button>
                                        )
                                    }
                                )}
                            </div>
                        </div>

                        {/* REMARKS */}
                        <div className="space-y-2">
                            <Label className="text-sm font-semibold">
                                Remarks
                            </Label>

                            <Textarea
                                value={
                                    form.remarks
                                }
                                onChange={(e) =>
                                    setForm(
                                        (prev) => ({
                                            ...prev,
                                            remarks:
                                            e
                                                .target
                                                .value,
                                        })
                                    )
                                }
                                placeholder="Add optional remarks..."
                                className="min-h-30 rounded-3xl border-muted-foreground/20"
                            />
                        </div>

                        <Separator />

                        {/* ACTIONS */}
                        <div className="flex items-center justify-end gap-3">
                            <Button
                                variant="outline"
                                className="rounded-2xl"
                                onClick={() =>
                                    setOpen(
                                        false
                                    )
                                }
                            >
                                Cancel
                            </Button>

                            <Button
                                onClick={
                                    handleSubmit
                                }
                                disabled={
                                    loading
                                }
                                className="rounded-2xl px-8"
                            >
                                {loading ? (
                                    <>
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />

                                        Saving...
                                    </>
                                ) : (
                                    <>
                                        <CheckCircle2 className="mr-2 h-4 w-4" />

                                        Save
                                        Attendance
                                    </>
                                )}
                            </Button>
                        </div>
                    </div>

                    {/* PREVIEW */}
                    <div className="border-l bg-muted/30 p-6">
                        <h3 className="mb-5 text-lg font-semibold">
                            Attendance
                            Preview
                        </h3>

                        <AnimatePresence mode="wait">
                            {selectedStudent ? (
                                <motion.div
                                    key={
                                        selectedStudent.id
                                    }
                                    initial={{
                                        opacity: 0,
                                        y: 10,
                                    }}
                                    animate={{
                                        opacity: 1,
                                        y: 0,
                                    }}
                                    exit={{
                                        opacity: 0,
                                    }}
                                >
                                    <Card className="rounded-3xl border-0 shadow-sm">
                                        <CardContent className="space-y-5 p-6">
                                            <div className="flex flex-col items-center text-center">
                                                <Avatar className="h-18 w-18">
                                                    <AvatarFallback className="text-xl font-bold">
                                                        {selectedStudent.user?.person?.first_name?.[0]}
                                                    </AvatarFallback>
                                                </Avatar>

                                                <h4 className="mt-4 text-lg font-bold">
                                                    {
                                                        selectedStudent
                                                            .user
                                                            ?.person
                                                            ?.first_name
                                                    }{' '}
                                                    {
                                                        selectedStudent
                                                            .user
                                                            ?.person
                                                            ?.last_name
                                                    }
                                                </h4>

                                                <p className="text-sm text-muted-foreground">
                                                    Student
                                                    Attendance
                                                    Record
                                                </p>
                                            </div>

                                            <Separator />

                                            <div className="space-y-4">
                                                <div className="flex items-center justify-between">
                                                    <span className="text-sm text-muted-foreground">
                                                        Date
                                                    </span>

                                                    <span className="font-medium">
                                                        {format(
                                                            date,
                                                            'PPP'
                                                        )}
                                                    </span>
                                                </div>

                                                <div className="flex items-center justify-between">
                                                    <span className="text-sm text-muted-foreground">
                                                        Status
                                                    </span>

                                                    <Badge
                                                        className={cn(
                                                            'rounded-full px-4 py-1',
                                                            ActiveStatus.className
                                                        )}
                                                    >
                                                        <ActiveStatus.icon className="mr-1 h-3.5 w-3.5" />

                                                        {
                                                            ActiveStatus.label
                                                        }
                                                    </Badge>
                                                </div>

                                                <div className="flex items-center justify-between">
                                                    <span className="text-sm text-muted-foreground">
                                                        Classroom
                                                    </span>

                                                    <span className="font-medium">
                                                        {classes.find((q)=>q.id===selectedStudent.class_id)?.name||
                                                            '--'}
                                                    </span>
                                                </div>
                                            </div>
                                        </CardContent>
                                    </Card>
                                </motion.div>
                            ) : (
                                <div className="flex h-full min-h-87.5 flex-col items-center justify-center rounded-3xl border border-dashed bg-background/70 p-8 text-center">
                                    <div className="rounded-full bg-primary/10 p-5 text-primary">
                                        <UserRound className="h-8 w-8" />
                                    </div>

                                    <h3 className="mt-5 text-lg font-semibold">
                                        No Student
                                        Selected
                                    </h3>

                                    <p className="mt-2 max-w-55 text-sm text-muted-foreground">
                                        Select a
                                        student to
                                        preview
                                        attendance
                                        details here.
                                    </p>
                                </div>
                            )}
                        </AnimatePresence>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}