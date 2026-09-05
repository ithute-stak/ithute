"use client"

import * as React from "react"
import { useAppDispatch, useAppSelector } from "@/store/hooks"
import { toast } from "sonner"

import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
    DialogFooter,
} from "@/components/ui/dialog"

import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"

import {
    Popover,
    PopoverTrigger,
    PopoverContent,
} from "@/components/ui/popover"

import {
    Command,
    CommandInput,
    CommandList,
    CommandEmpty,
    CommandGroup,
    CommandItem,
} from "@/components/ui/command"

import { Check, ChevronsUpDown, Plus } from "lucide-react"
import { cn } from "@/lib/utils"

import { GradeCreate } from "@/types/grade"

import {
    createClassThunk
} from "@/store/features/thunks/classThunks"

import {
    createGradeThunk,
    getGradesThunk
} from "@/store/features/thunks/gradeThunks"
import {ClassCreate} from "@/types/classes";

/* =========================
   TYPES
========================= */

type Grade = {
    id: string
    name: string
}

export function ClassRegisterDialog() {
    const dispatch = useAppDispatch()

    const { grades } = useAppSelector((state) => state.grade)
    const { loading } = useAppSelector((state) => state.class)

    const [open, setOpen] = React.useState(false)
    const [gradeOpen, setGradeOpen] = React.useState(false)
    const [gradeSearch, setGradeSearch] = React.useState("")

    const [gradeDialogOpen, setGradeDialogOpen] = React.useState(false)

    const [form, setForm] = React.useState<ClassCreate>({
        name: "",
        grade_id: "",
        school_id: "",
    })

    const [newGrade, setNewGrade] = React.useState<GradeCreate>({
        name: "",
    })

    /* =========================
       FILTERED GRADES
    ========================= */
    const filteredGrades = (grades ?? []).filter((g: Grade) =>
        g.name.toLowerCase().includes(gradeSearch.toLowerCase())
    )

    const selectedGrade = grades?.find(
        (g: Grade) => g.id === form.grade_id
    )

    /* =========================
       HANDLERS
    ========================= */

    const handleField = <K extends keyof ClassCreate>(
        key: K,
        value: ClassCreate[K]
    ) => {
        setForm((prev) => ({ ...prev, [key]: value }))
    }

    /* =========================
       CREATE CLASS
    ========================= */
    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()

        const res = await dispatch(createClassThunk(form))

        if (createClassThunk.fulfilled.match(res)) {
            toast.success("Class created")
            setOpen(false)
        } else {
            toast.error("Failed to create class")
        }
    }

    /* =========================
       CREATE GRADE INLINE
    ========================= */
    const handleCreateGrade = async () => {
        const res = await dispatch(createGradeThunk(newGrade))

        if (createGradeThunk.fulfilled.match(res)) {
            toast.success("Grade added")

            setGradeDialogOpen(false)
            setNewGrade({ name: "" })

            dispatch(getGradesThunk()) // refresh list
        } else {
            toast.error("Failed to add grade")
        }
    }

    return (
        <>
            {/* ================= MAIN DIALOG ================= */}
            <Dialog open={open} onOpenChange={setOpen}>
                <DialogTrigger asChild>
                    <Button>
                        <Plus className="size-4" />
                    </Button>
                </DialogTrigger>

                <DialogContent className="sm:max-w-xl rounded-2xl">
                    <DialogHeader>
                        <DialogTitle>Create Class</DialogTitle>
                    </DialogHeader>

                    <form onSubmit={handleSubmit} className="space-y-6">

                        {/* ================= CLASS NAME ================= */}
                        <div>
                            <Label>Class Name</Label>
                            <Input
                                placeholder="A, B, C..."
                                value={form.name}
                                onChange={(e) =>
                                    handleField("name", e.target.value)
                                }
                            />
                        </div>

                        {/* ================= GRADE SELECT + ADD ================= */}
                        <div className="space-y-2">
                            <Label>Grade</Label>

                            <div className="flex gap-2">
                                {/* SEARCH SELECT */}
                                <Popover
                                    open={gradeOpen}
                                    onOpenChange={setGradeOpen}
                                >
                                    <PopoverTrigger asChild>
                                        <Button
                                            variant="outline"
                                            className="flex-1 justify-between"
                                        >
                                            {selectedGrade
                                                ? selectedGrade.name
                                                : "Select grade"}
                                            <ChevronsUpDown className="ml-2 h-4 w-4 opacity-50" />
                                        </Button>
                                    </PopoverTrigger>

                                    <PopoverContent className="w-[250px] p-0">
                                        <Command>
                                            <CommandInput
                                                placeholder="Search grade..."
                                                value={gradeSearch}
                                                onValueChange={setGradeSearch}
                                            />

                                            <CommandList>
                                                <CommandEmpty>
                                                    No grade found
                                                </CommandEmpty>

                                                <CommandGroup>
                                                    {filteredGrades.map(
                                                        (g: Grade) => (
                                                            <CommandItem
                                                                key={g.id}
                                                                value={g.name}
                                                                onSelect={() => {
                                                                    handleField(
                                                                        "grade_id",
                                                                        g.id
                                                                    )
                                                                    setGradeOpen(
                                                                        false
                                                                    )
                                                                }}
                                                            >
                                                                <Check
                                                                    className={cn(
                                                                        "mr-2 h-4 w-4",
                                                                        form.grade_id ===
                                                                        g.id
                                                                            ? "opacity-100"
                                                                            : "opacity-0"
                                                                    )}
                                                                />
                                                                {g.name}
                                                            </CommandItem>
                                                        )
                                                    )}
                                                </CommandGroup>
                                            </CommandList>
                                        </Command>
                                    </PopoverContent>
                                </Popover>

                                {/* ADD GRADE BUTTON */}
                                <Button
                                    type="button"
                                    size="icon"
                                    variant="secondary"
                                    onClick={() =>
                                        setGradeDialogOpen(true)
                                    }
                                >
                                    <Plus className="h-4 w-4" />
                                </Button>
                            </div>
                        </div>

                        <DialogFooter>
                            <Button type="submit" disabled={loading}>
                                {loading
                                    ? "Creating..."
                                    : "Create Class"}
                            </Button>
                        </DialogFooter>
                    </form>
                </DialogContent>
            </Dialog>

            {/* ================= ADD GRADE DIALOG ================= */}
            <Dialog
                open={gradeDialogOpen}
                onOpenChange={setGradeDialogOpen}
            >
                <DialogContent className="sm:max-w-md rounded-2xl">
                    <DialogHeader>
                        <DialogTitle>Add Grade</DialogTitle>
                    </DialogHeader>

                    <div className="space-y-4">
                        <Input
                            placeholder="Grade name"
                            value={newGrade.name}
                            onChange={(e) =>
                                setNewGrade({
                                    name: e.target.value,
                                })
                            }
                        />
                    </div>

                    <DialogFooter>
                        <Button onClick={handleCreateGrade}>
                            Save Grade
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    )
}