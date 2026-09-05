"use client"

import * as React from "react"
import { format } from "date-fns"
import {
    Calendar as CalendarIcon,
    Clock3,
    MapPin,
    Users,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

import { Calendar } from "@/components/ui/calendar"
import {AddEventDialog, EventForm} from "@/app/(dashboard)/dashboard/_components/_components/addEvent";
import {EventCard} from "@/app/(dashboard)/dashboard/_components/_components/eventCard";

/* =============================
   TYPES
============================= */

export interface EventItem {
    id: number
    title: string
    type: "Exam" | "Meeting" | "Sports" | "Holiday" | "Parent Day"
    date: Date
    time: string
    location: string
    attendees: string
    description: string
}


const initialEvents: EventItem[] = [
    {
        id: 1,
        title: "Mid-Term Exams",
        type: "Exam",
        date: new Date(Date.now() + 24 * 60 * 60 * 1000),
        time: "08:00 AM",
        location: "Main Hall",
        attendees: "All Students",
        description: "Grade-wide academic examinations.",
    },
]

const defaultForm: EventForm = {
    title: "",
    type: "Meeting",
    time: "",
    location: "",
    attendees: "",
    description: "",
}



/* =============================
   HELPERS
============================= */

const isSameDay = (d1: Date, d2: Date) =>
    format(d1, "yyyy-MM-dd") === format(d2, "yyyy-MM-dd")


export default function EventCalendar() {
    const [date, setDate] = React.useState<Date | undefined>(new Date())
    const [events, setEvents] = React.useState<EventItem[]>(initialEvents)
    const [open, setOpen] = React.useState(false)
    const [form, setForm] = React.useState<EventForm>(defaultForm)

    const eventDates = events.map((e) => e.date)

    const selectedDateEvents = events.filter(
        (event) => date && isSameDay(event.date, date)
    )

    const handleCreateEvent = () => {
        if (!date || !form.title || !form.time) return

        const newEvent: EventItem = {
            id: Date.now(),
            title: form.title,
            type: form.type as EventItem["type"],
            date,
            time: form.time,
            location: form.location,
            attendees: form.attendees,
            description: form.description,
        }

        setEvents((prev) => [...prev, newEvent])
        setForm(defaultForm)
        setOpen(false)
    }

    return (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 p-4 lg:p-6">
            <Card className="lg:col-span-2 rounded-2xl border-border shadow-sm">
                <CardHeader className="flex flex-row items-center justify-between">
                    <CardTitle className="text-lg font-semibold">School Calendar</CardTitle>

                    <AddEventDialog
                        open={open}
                        setOpen={setOpen}
                        form={form}
                        setForm={setForm}
                        onSave={handleCreateEvent}
                    />
                </CardHeader>

                <CardContent>
                    <Calendar
                        mode="single"
                        selected={date}
                        onSelect={setDate}
                        className="rounded-xl border bg-muted/30 p-3 w-full"
                        modifiers={{
                            hasEvent: (day) =>
                                eventDates.some((eventDate) => isSameDay(eventDate, day)),
                        }}
                        modifiersClassNames={{
                            hasEvent: `bg-red-100 text-red-600 border-red-200 relative font-semibold after:absolute after:bottom-1 after:left-1/2 after:-translate-x-1/2 after:h-1.5 after:w-1.5 after:rounded-full after:bg-primary`

                        }}
                    />
                </CardContent>
            </Card>

            <Card className="lg:col-span-3 rounded-2xl border-border shadow-sm">
                <CardHeader>
                    <CardTitle>
                        {date ? format(date, "MMMM dd, yyyy") : "Select a date"}
                    </CardTitle>
                </CardHeader>

                <CardContent className="space-y-4">
                    {selectedDateEvents.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                            <CalendarIcon className="size-8 mb-2 opacity-50" />
                            <p>No events for this day</p>
                        </div>
                    ) : (
                        selectedDateEvents.map((event) => (
                            <EventCard key={event.id} event={event} />
                        ))
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
