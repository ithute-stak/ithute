import * as React from "react";
import {EventItem} from "@/app/(dashboard)/dashboard/_components/event_calender";
import {Card, CardContent} from "@/components/ui/card";
import {CalendarIcon, Clock3, MapPin, Users} from "lucide-react";
import {format} from "date-fns";
import {Badge} from "@/components/ui/badge";

export const typeColors: Record<EventItem["type"], string> = {
    Exam: "bg-red-100 text-red-600 border-red-200",
    Meeting: "bg-blue-100 text-blue-600 border-blue-200",
    Sports: "bg-green-100 text-green-600 border-green-200",
    Holiday: "bg-yellow-100 text-yellow-700 border-yellow-200",
    "Parent Day": "bg-purple-100 text-purple-600 border-purple-200",
}
export function EventCard({ event }: { event: EventItem }) {
    return (
        <Card className="rounded-2xl border hover:shadow-md transition-shadow">
            <CardContent className="p-5 space-y-3">
                <div className="flex items-center justify-between">
                    <h3 className="font-semibold">{event.title}</h3>
                    <Badge className={typeColors[event.type]}>{event.type}</Badge>
                </div>

                <div className="grid gap-2 text-sm text-muted-foreground">
                    <div className="flex items-center gap-2">
                        <Clock3 className="size-4" />
                        {event.time}
                    </div>

                    <div className="flex items-center gap-2">
                        <MapPin className="size-4" />
                        {event.location}
                    </div>

                    <div className="flex items-center gap-2">
                        <Users className="size-4" />
                        {event.attendees}
                    </div>

                    <div className="flex items-center gap-2">
                        <CalendarIcon className="size-4" />
                        {format(event.date, "MMMM dd, yyyy")}
                    </div>
                </div>

                <p className="text-sm">{event.description}</p>
            </CardContent>
        </Card>
    )
}