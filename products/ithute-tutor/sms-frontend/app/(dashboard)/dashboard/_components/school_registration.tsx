"use client"

import React, {useState} from "react"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog"

import {Button} from "@/components/ui/button"
import {Input} from "@/components/ui/input"
import {Label} from "@/components/ui/label"
import {Select, SelectContent, SelectItem, SelectTrigger, SelectValue} from "@/components/ui/select"

import {Plus} from "lucide-react"
import {useAppDispatch} from "@/store/hooks";
import {createSchoolThunk} from "@/store/features/thunks/schoolThunks";
import {SchoolCategory} from "@/types/school";
import {toast} from "sonner";

export function SchoolRegisterDialog() {
    const [open, setOpen] = useState(false)
    const dispatch = useAppDispatch()

    const [form, setForm] = useState<{
        name: string;
        school_code: string;
        registration_number: string;
        category: SchoolCategory;
    }>({
        name: "",
        school_code: "",
        registration_number: "",
        category: SchoolCategory.primary_school,
    });

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setForm({...form, [e.target.name]: e.target.value})
    }

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault(); // ✅ STOP reload

        try {
            await dispatch(createSchoolThunk(form)).unwrap();

            toast.success("School created successfully");

            setOpen(false); // ✅ close dialog
        } catch (err) {
            toast.error(String(err));
        }
    };

    return (
        <Dialog open={open} onOpenChange={setOpen}>

            {/* TRIGGER BUTTON */}
            <DialogTrigger asChild>
                <Button className="gap-2">
                    <Plus className="size-4"/>
                </Button>
            </DialogTrigger>

            {/* DIALOG CONTENT */}
            <DialogContent className="sm:max-w-130">
                <DialogHeader>
                    <DialogTitle>Register New School</DialogTitle>
                    <DialogDescription>
                        Add a new school to the management system.
                    </DialogDescription>
                </DialogHeader>

                <form onSubmit={handleCreate} className="grid gap-4 mt-4">

                    {/* NAME */}
                    <div className="grid gap-2">
                        <Label>School Name</Label>
                        <Input
                            name="name"
                            value={form.name}
                            onChange={handleChange}
                            placeholder="e.g. Maseru High School"
                        />
                    </div>

                    {/* SCHOOL CODE */}
                    <div className="grid gap-2">
                        <Label>School Code</Label>
                        <Input
                            name="school_code"
                            value={form.school_code}
                            onChange={handleChange}
                            placeholder="e.g. MHS-001"
                        />
                    </div>

                    {/* REG NUMBER */}
                    <div className="grid gap-2">
                        <Label>Registration Number</Label>
                        <Input
                            name="registration_number"
                            value={form.registration_number}
                            onChange={handleChange}
                            placeholder="e.g. REG-2026-001"
                        />
                    </div>

                    {/* CATEGORY */}
                    <div className="grid gap-2">
                        <Label>Category</Label>
                        <Select
                            value={form.category}
                            onValueChange={(value) =>
                                setForm((prev) => ({
                                    ...prev,
                                    category: value as SchoolCategory,
                                }))
                            }
                        >
                            {/* TRIGGER */}
                            <SelectTrigger>
                                <SelectValue placeholder="Select category" />
                            </SelectTrigger>

                            {/* CONTENT (THIS IS REQUIRED) */}
                            <SelectContent>
                                {Object.values(SchoolCategory).map((cat) => (
                                    <SelectItem key={cat} value={cat}>
                                        {cat.replaceAll("_", " ")}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    {/* ACTIONS */}
                    <div className="flex justify-end gap-2 pt-2">
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => setOpen(false)}
                        >
                            Cancel
                        </Button>

                        <Button type="submit">
                            Save School
                        </Button>
                    </div>

                </form>
            </DialogContent>
        </Dialog>
    )
}