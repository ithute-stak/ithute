"use client"

import * as React from "react"
import {
    closestCenter,
    DndContext,
    DragEndEvent,
    KeyboardSensor,
    MouseSensor,
    TouchSensor,
    useSensor,
    useSensors,
} from "@dnd-kit/core"

import {restrictToVerticalAxis} from "@dnd-kit/modifiers"
import {arrayMove, SortableContext, useSortable, verticalListSortingStrategy,} from "@dnd-kit/sortable"

import {CSS} from "@dnd-kit/utilities"

import {
    ColumnDef,
    flexRender,
    getCoreRowModel,
    getFilteredRowModel,
    getPaginationRowModel,
    getSortedRowModel,
    Row,
    useReactTable,
} from "@tanstack/react-table"

import {Table, TableBody, TableCell, TableHead, TableHeader, TableRow,} from "@/components/ui/table"

import {Input} from "@/components/ui/input"
import {Button} from "@/components/ui/button"
import {Badge} from "@/components/ui/badge"
import {DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,} from "@/components/ui/dropdown-menu"

import {EllipsisVerticalIcon, GripVerticalIcon, Search,} from "lucide-react"

import {StudentRead} from "@/types/student"
import {GenderEnum, UserRole} from "@/types/shared.primitive"

/* ================= TYPES ================= */

export type StudentRow = {
    id: string
    admission_number: string
    class_id: string | null
    username: string
    email: string
    role: UserRole
    first_name: string
    last_name: string
    gender: GenderEnum
    date_of_birth: string
    nationality: string
    national_id: string | null
}

/* ================= TRANSFORM ================= */

export function transformStudents(data: StudentRead[]): StudentRow[] {
    return data.filter((q)=>q.user.role===UserRole.student).map((item) => {
        const user = item.user
        const person = user?.person

        return {
            id: item.id,
            admission_number: item.admission_number ?? "",
            class_id: item.class_id ?? null,
            username: user?.username ?? "",
            email: user?.email ?? "",
            role: user?.role ?? UserRole.student,
            first_name: person?.first_name ?? "",
            last_name: person?.last_name ?? "",
            gender: person?.gender ?? GenderEnum.male,
            date_of_birth: person?.date_of_birth ?? "",
            nationality: person?.nationality ?? "",
            national_id: person?.national_id ?? null,
        }
    })
}

/* ================= DRAG HANDLE ================= */

function DragHandle({ id }: { id: string }) {
    const { attributes, listeners } = useSortable({ id })

    return (
        <Button variant="ghost" size="icon" {...attributes} {...listeners}>
            <GripVerticalIcon className="size-4" />
        </Button>
    )
}

/* ================= COLUMNS ================= */

const columns: ColumnDef<StudentRow>[] = [
    {
        id: "drag",
        header: () => null,
        cell: ({ row }) => <DragHandle id={row.original.id} />,
    },
    {
        accessorKey: "admission_number",
        header: "Admission No",
    },
    {
        header: "Name",
        cell: ({ row }) =>
            `${row.original.first_name} ${row.original.last_name}`,
    },
    {
        accessorKey: "email",
        header: "Email",
    },
    {
        accessorKey: "gender",
        header: "Gender",
        cell: ({ row }) => (
            <Badge variant="outline">{row.original.gender}</Badge>
        ),
    },
    {
        accessorKey: "nationality",
        header: "Nationality",
    },
    {
        accessorKey: "role",
        header: "Role",
        cell: ({ row }) => (
            <Badge variant="secondary">{row.original.role}</Badge>
        ),
    },
    {
        id: "actions",
        cell: () => (
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon">
                        <EllipsisVerticalIcon />
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                    <DropdownMenuItem>Edit</DropdownMenuItem>
                    <DropdownMenuItem className="text-red-500">
                        Delete
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>
        ),
    },
]

/* ================= ROW ================= */

function DraggableRow({ row }: { row: Row<StudentRow> }) {
    const { transform, transition, setNodeRef } = useSortable({
        id: row.original.id,
    })

    return (
        <TableRow
            ref={setNodeRef}
            style={{
                transform: CSS.Transform.toString(transform),
                transition,
            }}
        >
            {row.getVisibleCells().map((cell) => (
                <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </TableCell>
            ))}
        </TableRow>
    )
}

/* ================= MAIN TABLE ================= */

export function SchoolTable({ data }: { data: StudentRead[] }) {
    const tableData = React.useMemo(() => transformStudents(data), [data])

    const [orderedIds, setOrderedIds] = React.useState<string[]>([])
    const [globalFilter, setGlobalFilter] = React.useState("")

    React.useEffect(() => {
        setOrderedIds(tableData.map((d) => d.id))
    }, [tableData])

    const orderedData = React.useMemo(() => {
        const map = new Map(tableData.map((d) => [d.id, d]))
        return orderedIds.map((id) => map.get(id)).filter(Boolean) as StudentRow[]
    }, [tableData, orderedIds])

    const sensors = useSensors(
        useSensor(MouseSensor),
        useSensor(TouchSensor),
        useSensor(KeyboardSensor)
    )

    function handleDragEnd(event: DragEndEvent) {
        const { active, over } = event
        if (!over || active.id === over.id) return

        setOrderedIds((prev) => {
            const oldIndex = prev.indexOf(active.id as string)
            const newIndex = prev.indexOf(over.id as string)
            return arrayMove(prev, oldIndex, newIndex)
        })
    }

    const table = useReactTable({
        data: orderedData,
        columns,
        state: { globalFilter },
        onGlobalFilterChange: setGlobalFilter,
        getCoreRowModel: getCoreRowModel(),
        getFilteredRowModel: getFilteredRowModel(),
        getSortedRowModel: getSortedRowModel(),
        getPaginationRowModel: getPaginationRowModel(),
    })

    const dataIds = React.useMemo(
        () => orderedData.map((d) => d.id),
        [orderedData]
    )

    return (
        <div className="space-y-4">

            {/* ================= SaaS TOOLBAR ================= */}
            <div className="flex flex-col md:flex-row gap-3 md:items-center md:justify-between">

                {/* SEARCH */}
                <div className="relative w-full md:w-1/3">
                    <Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" />
                    <Input
                        placeholder="Search students..."
                        value={globalFilter}
                        onChange={(e) => setGlobalFilter(e.target.value)}
                        className="pl-9"
                    />
                </div>

                {/* QUICK STATS */}
                <div className="flex gap-2">
                    <Badge variant="outline">
                        Total: {orderedData.length}
                    </Badge>
                </div>
            </div>

            {/* ================= TABLE ================= */}
            <div className="rounded-xl border overflow-hidden">
                <DndContext
                    collisionDetection={closestCenter}
                    modifiers={[restrictToVerticalAxis]}
                    onDragEnd={handleDragEnd}
                    sensors={sensors}
                >
                    <Table>
                        <TableHeader>
                            {table.getHeaderGroups().map((hg) => (
                                <TableRow key={hg.id}>
                                    {hg.headers.map((header) => (
                                        <TableHead key={header.id}>
                                            {flexRender(
                                                header.column.columnDef.header,
                                                header.getContext()
                                            )}
                                        </TableHead>
                                    ))}
                                </TableRow>
                            ))}
                        </TableHeader>

                        <TableBody>
                            <SortableContext
                                items={dataIds}
                                strategy={verticalListSortingStrategy}
                            >
                                {table.getRowModel().rows.map((row) => (
                                    <DraggableRow key={row.id} row={row} />
                                ))}
                            </SortableContext>
                        </TableBody>
                    </Table>
                </DndContext>
            </div>

            {/* ================= PAGINATION ================= */}
            <div className="flex items-center justify-between">
                <Button
                    variant="outline"
                    onClick={() => table.previousPage()}
                    disabled={!table.getCanPreviousPage()}
                >
                    Previous
                </Button>

                <span className="text-sm text-muted-foreground">
                    Page {table.getState().pagination?.pageIndex + 1}
                </span>

                <Button
                    variant="outline"
                    onClick={() => table.nextPage()}
                    disabled={!table.getCanNextPage()}
                >
                    Next
                </Button>
            </div>
        </div>
    )
}