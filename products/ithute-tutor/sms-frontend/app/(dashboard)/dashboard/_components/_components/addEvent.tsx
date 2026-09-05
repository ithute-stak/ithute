import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog"
import {Input} from "@/components/ui/input"
import {Label} from "@/components/ui/label"
import {Textarea} from "@/components/ui/textarea"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import {Button} from "@/components/ui/button";
import {Plus} from "lucide-react";
import React from "react";
export type EventForm = {
    title: string
    type: string
    time: string
    location: string
    attendees: string
    description: string
}
export function AddEventDialog({open, setOpen, form, setForm, onSave}: {
    open: boolean
    setOpen: (value: boolean) => void
    form: EventForm
    setForm: React.Dispatch<React.SetStateAction<EventForm>>
    onSave: () => void
}) {
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button size="sm" className="rounded-xl">
                    <Plus className="mr-2 size-4"/>
                    Add Event
                </Button>
            </DialogTrigger>

            <DialogContent className="sm:max-w-lg rounded-2xl">
                <DialogHeader>
                    <DialogTitle>Create School Event</DialogTitle>
                </DialogHeader>

                <div className="grid gap-4 py-2">
                    <div className="grid gap-2">
                        <Label>Event Title</Label>
                        <Input
                            value={form.title}
                            onChange={(e) => setForm((p) => ({...p, title: e.target.value}))}
                        />
                    </div>

                    <div className="grid gap-2">
                        <Label>Event Type</Label>
                        <Select
                            value={form.type}
                            onValueChange={(value) => setForm((p) => ({...p, type: value}))}
                        >
                            <SelectTrigger>
                                <SelectValue/>
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="Exam">Exam</SelectItem>
                                <SelectItem value="Meeting">Meeting</SelectItem>
                                <SelectItem value="Sports">Sports</SelectItem>
                                <SelectItem value="Holiday">Holiday</SelectItem>
                                <SelectItem value="Parent Day">Parent Day</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    <div className="grid md:grid-cols-2 gap-4">
                        <div className="grid gap-2">
                            <Label>Time</Label>
                            <Input
                                placeholder="09:00 AM"
                                value={form.time}
                                onChange={(e) => setForm((p) => ({...p, time: e.target.value}))}
                            />
                        </div>

                        <div className="grid gap-2">
                            <Label>Location</Label>
                            <Input
                                value={form.location}
                                onChange={(e) => setForm((p) => ({...p, location: e.target.value}))}
                            />
                        </div>
                    </div>

                    <div className="grid gap-2">
                        <Label>Attendees</Label>
                        <Input
                            value={form.attendees}
                            onChange={(e) => setForm((p) => ({...p, attendees: e.target.value}))}
                        />
                    </div>

                    <div className="grid gap-2">
                        <Label>Description</Label>
                        <Textarea
                            value={form.description}
                            onChange={(e) => setForm((p) => ({...p, description: e.target.value}))}
                        />
                    </div>

                    <Button onClick={onSave} className="rounded-xl">
                        Save Event
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    )
}