// components/school-fee/FeeConfigRow.tsx

'use client'

import * as React from 'react'

import { format } from 'date-fns'

import {
    ChevronDown,
    ChevronRight,
} from 'lucide-react'

import {
    TableCell,
    TableRow,
} from '@/components/ui/table'

import { Badge } from '@/components/ui/badge'

import { Button } from '@/components/ui/button'

import { useAppData } from '@/provider/dataProvider'

import { FeeConfigActions } from '@/app/(dashboard)/dashboard/settings/_components/feeConfigAction'

import { SchoolFeeConfigurationRead } from '@/types/finance/schoolFeeConfiguration'
import {FeePlansExpanded} from "@/app/(dashboard)/dashboard/settings/_components/feePlanExpanded";


interface Props {
    item: SchoolFeeConfigurationRead

    expanded: boolean

    onToggle: () => void

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

export function FeeConfigRow({
                                 item,
                                 expanded,
                                 onToggle,
                                 onEdit,
                                 onDelete,
                                 onAddPlan,
                             }: Props) {
    const { schools } = useAppData()

    const schoolName =
        schools.find(
            (school) =>
                school.id === item.school_id
        )?.name ?? 'Unknown School'

    return (
        <>
            {/* ================= MAIN ROW ================= */}

            <TableRow className="hover:bg-muted/40">

                {/* expand */}
                <TableCell>
                    <Button
                        size="icon"
                        variant="ghost"
                        className="
                            h-8
                            w-8
                            rounded-xl
                        "
                        onClick={onToggle}
                    >
                        {expanded ? (
                            <ChevronDown className="h-4 w-4" />
                        ) : (
                            <ChevronRight className="h-4 w-4" />
                        )}
                    </Button>
                </TableCell>

                {/* school */}
                <TableCell>
                    <Badge className="rounded-full capitalize">
                        {schoolName}
                    </Badge>
                </TableCell>

                {/* structure */}
                <TableCell>
                    <Badge className="rounded-full capitalize">
                        {item.fee_structure}
                    </Badge>
                </TableCell>

                {/* year */}
                <TableCell>
                    <div className="space-y-1">
                        <p>
                            {format(
                                new Date(
                                    item.year_start
                                ),
                                'PPP'
                            )}
                        </p>

                        <p
                            className="
                                text-xs
                                text-muted-foreground
                            "
                        >
                            to{' '}
                            {format(
                                new Date(
                                    item.year_end
                                ),
                                'PPP'
                            )}
                        </p>
                    </div>
                </TableCell>

                {/* partial */}
                <TableCell>
                    <Badge
                        variant={
                            item.allow_partial_payments
                                ? 'default'
                                : 'secondary'
                        }
                        className="rounded-full"
                    >
                        {item.allow_partial_payments
                            ? 'Enabled'
                            : 'Disabled'}
                    </Badge>
                </TableCell>

                {/* late */}
                <TableCell>
                    <Badge
                        variant={
                            item.allow_late_payments
                                ? 'default'
                                : 'secondary'
                        }
                        className="rounded-full"
                    >
                        {item.allow_late_payments
                            ? 'Enabled'
                            : 'Disabled'}
                    </Badge>
                </TableCell>

                {/* actions */}
                <TableCell>
                    <FeeConfigActions
                        item={item}
                        onEdit={onEdit}
                        onDelete={onDelete}
                        onAddPlan={onAddPlan}
                    />
                </TableCell>
            </TableRow>

            {/* ================= EXPANDED ================= */}

            {expanded && (
                <FeePlansExpanded
                    feeConfigId={item.id}
                />
            )}
        </>
    )
}