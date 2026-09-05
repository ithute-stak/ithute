// components/school-fee/FeeConfigTable.tsx

'use client'

import * as React from 'react'

import {
    Table,
    TableBody,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'

import { SchoolFeeConfigurationRead } from '@/types/finance/schoolFeeConfiguration'
import {FeeConfigRow} from "@/app/(dashboard)/dashboard/settings/_components/feeConfigRaw";


interface Props {
    configurations: SchoolFeeConfigurationRead[]

    onEdit: (
        item: SchoolFeeConfigurationRead
    ) => void

    onDelete: (
        item: SchoolFeeConfigurationRead
    ) => void

    onAddPlan: (
        item: SchoolFeeConfigurationRead
    ) => void
}

export function FeeConfigTable({
                                   configurations,
                                   onEdit,
                                   onDelete,
                                   onAddPlan,
                               }: Props) {
    const [expandedRows, setExpandedRows] =
        React.useState<string[]>([])

    const toggleRow = (id: string) => {
        setExpandedRows((prev) =>
            prev.includes(id)
                ? prev.filter(
                    (item) => item !== id
                )
                : [...prev, id]
        )
    }

    return (
        <Table>

            {/* ================= HEADER ================= */}

            <TableHeader>
                <TableRow>
                    <TableHead className="w-12" />

                    <TableHead>
                        School
                    </TableHead>

                    <TableHead>
                        Structure
                    </TableHead>

                    <TableHead>
                        Academic Year
                    </TableHead>

                    <TableHead>
                        Partial
                    </TableHead>

                    <TableHead>
                        Late
                    </TableHead>

                    <TableHead className="text-right">
                        Actions
                    </TableHead>
                </TableRow>
            </TableHeader>

            {/* ================= BODY ================= */}

            <TableBody>
                {configurations.map((item) => (
                    <FeeConfigRow
                        key={item.id}
                        item={item}
                        expanded={
                            expandedRows.includes(
                                item.id
                            )
                        }
                        onToggle={() =>
                            toggleRow(item.id)
                        }
                        onEdit={onEdit}
                        onDelete={onDelete}
                        onAddPlan={onAddPlan}
                    />
                ))}
            </TableBody>
        </Table>
    )
}