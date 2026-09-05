import {StudentRead} from "@/types/student"
import {ClassResponse} from "@/types/classes"

import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table"

import {Badge} from "@/components/ui/badge"
import {Button} from "@/components/ui/button"

import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

import {
    Eye,
    MoreHorizontal,
    Pencil,
    Trash2,
    User2,
    GraduationCap,
    Globe2,
    VenusAndMars,
    Hash,
} from "lucide-react"

import {calculateAge} from "@/lib/person_age"

export function AllStudentTable({
                                    filtered,
                                    classes,
                                }: {
    filtered: StudentRead[]
    classes: ClassResponse[]
}) {
    return (
        <Table>

            {/* ================= HEADER ================= */}

            <TableHeader
                className="
                    sticky
                    top-0
                    z-10
                    bg-background
                    backdrop-blur
                "
            >
                <TableRow
                    className="
                        border-b
                        bg-muted/30
                        hover:bg-muted/30
                    "
                >

                    <TableHead className="pl-6">
                        <div className="flex items-center gap-2">
                            <Hash className="h-4 w-4 text-muted-foreground"/>
                            Admission
                        </div>
                    </TableHead>

                    <TableHead>
                        <div className="flex items-center gap-2">
                            <User2 className="h-4 w-4 text-muted-foreground"/>
                            Student
                        </div>
                    </TableHead>

                    <TableHead>
                        <div className="flex items-center gap-2">
                            <VenusAndMars className="h-4 w-4 text-muted-foreground"/>
                            Gender
                        </div>
                    </TableHead>

                    <TableHead>
                        <div className="flex items-center gap-2">
                            <Globe2 className="h-4 w-4 text-muted-foreground"/>
                            Nationality
                        </div>
                    </TableHead>

                    <TableHead>
                        <div className="flex items-center gap-2">
                            <GraduationCap className="h-4 w-4 text-muted-foreground"/>
                            Class
                        </div>
                    </TableHead>

                    <TableHead>
                        Age
                    </TableHead>

                    <TableHead className="pr-6 text-right">
                        Actions
                    </TableHead>
                </TableRow>
            </TableHeader>

            {/* ================= BODY ================= */}

            <TableBody>

                {/* EMPTY STATE */}

                {filtered.length === 0 && (
                    <TableRow>

                        <TableCell
                            colSpan={7}
                            className="
                                h-52
                                text-center
                            "
                        >

                            <div
                                className="
                                    flex
                                    flex-col
                                    items-center
                                    justify-center
                                    gap-3
                                "
                            >

                                <div
                                    className="
                                        flex
                                        h-16
                                        w-16
                                        items-center
                                        justify-center
                                        rounded-3xl
                                        bg-muted
                                    "
                                >
                                    <User2
                                        className="
                                            h-7
                                            w-7
                                            text-muted-foreground
                                        "
                                    />
                                </div>

                                <div className="space-y-1">
                                    <h3 className="font-semibold">
                                        No students found
                                    </h3>

                                    <p
                                        className="
                                            text-sm
                                            text-muted-foreground
                                        "
                                    >
                                        Try adjusting your filters or
                                        search query.
                                    </p>
                                </div>
                            </div>
                        </TableCell>
                    </TableRow>
                )}

                {/* ROWS */}

                {filtered.map((student: StudentRead) => {

                    const fullName = `
                        ${student.user.person?.first_name ?? ""}
                        ${student.user.person?.last_name ?? ""}
                    `

                    const className =
                        classes.find(
                            (c) =>
                                c.id === student.class_id
                        )?.name ?? "Unassigned"

                    return (
                        <TableRow
                            key={student.id}
                            className="
                                group
                                border-b
                                transition-all
                                hover:bg-muted/30
                            "
                        >

                            {/* ADMISSION */}

                            <TableCell className="pl-6">

                                <Badge
                                    variant="secondary"
                                    className="
                                        rounded-full
                                        px-3
                                        py-1
                                        font-medium
                                    "
                                >
                                    {student.admission_number}
                                </Badge>
                            </TableCell>

                            {/* STUDENT */}

                            <TableCell>

                                <div
                                    className="
                                        flex
                                        items-center
                                        gap-3
                                    "
                                >

                                    {/* AVATAR */}

                                    <div
                                        className="
                                            flex
                                            h-11
                                            w-11
                                            items-center
                                            justify-center
                                            rounded-2xl
                                            bg-primary/10
                                            font-bold
                                            text-primary
                                        "
                                    >
                                        {student.user.person?.first_name?.[0]}
                                        {student.user.person?.last_name?.[0]}
                                    </div>

                                    {/* INFO */}

                                    <div className="space-y-0.5">

                                        <p
                                            className="
                                                font-semibold
                                                tracking-tight
                                            "
                                        >
                                            {fullName}
                                        </p>

                                        <p
                                            className="
                                                text-xs
                                                text-muted-foreground
                                            "
                                        >
                                            {student.user.email}
                                        </p>
                                    </div>
                                </div>
                            </TableCell>

                            {/* GENDER */}

                            <TableCell>

                                <Badge
                                    variant="outline"
                                    className="
                                        rounded-full
                                        capitalize
                                    "
                                >
                                    {student.user.person?.gender}
                                </Badge>
                            </TableCell>

                            {/* NATIONALITY */}

                            <TableCell>

                                <div
                                    className="
                                        flex
                                        items-center
                                        gap-2
                                    "
                                >

                                    <div
                                        className="
                                            h-2
                                            w-2
                                            rounded-full
                                            bg-primary
                                        "
                                    />

                                    <span className="font-medium">
                                        {
                                            student.user.person
                                                ?.nationality
                                        }
                                    </span>
                                </div>
                            </TableCell>

                            {/* CLASS */}

                            <TableCell>

                                <Badge
                                    variant="secondary"
                                    className="
                                        rounded-full
                                        px-3
                                        py-1
                                    "
                                >
                                    {className}
                                </Badge>
                            </TableCell>

                            {/* AGE */}

                            <TableCell>

                                <Badge
                                    className="
                                        rounded-full
                                        px-3
                                        py-1
                                    "
                                >
                                    {calculateAge(
                                        student.user.person
                                            ?.date_of_birth ?? ""
                                    )}
                                </Badge>
                            </TableCell>

                            {/* ACTIONS */}

                            {/* ACTIONS */}

                            <TableCell className="pr-6 text-right">

                                <DropdownMenu>

                                    <DropdownMenuTrigger asChild>
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            className="rounded-2xl text-muted-foreground transition-all  hover:bg-muted hover:text-foreground md:opacity-100 data-[state=open]:opacity-100 ">
                                            <MoreHorizontal className="h-4 w-4 text-red-500"/>
                                        </Button>
                                    </DropdownMenuTrigger>

                                    <DropdownMenuContent
                                        align="end"
                                        className="w-48 rounded-2xl " >

                                        <DropdownMenuItem>
                                            <Eye className="mr-2 h-4 w-4"/>
                                            View Student
                                        </DropdownMenuItem>

                                        <DropdownMenuItem>
                                            <Pencil className="mr-2 h-4 w-4"/>
                                            Edit Student
                                        </DropdownMenuItem>

                                        <DropdownMenuItem
                                            className=" text-red-600focus:text-red-600">
                                            <Trash2 className="mr-2 h-4 w-4"/>
                                            Delete Student
                                        </DropdownMenuItem>
                                    </DropdownMenuContent>
                                </DropdownMenu>
                            </TableCell>
                        </TableRow>
                    )
                })}
            </TableBody>
        </Table>
    )
}