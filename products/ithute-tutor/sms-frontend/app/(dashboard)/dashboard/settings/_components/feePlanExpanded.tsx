// components/school-fee/FeePlansExpanded.tsx

'use client'

import * as React from 'react'

import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'

import { Badge } from '@/components/ui/badge'

import { useAppData } from '@/provider/dataProvider'

interface Props {
    feeConfigId: string
}

export function FeePlansExpanded({
                                     feeConfigId,
                                 }: Props) {
    const { grade, feePlans } = useAppData()

    const plans = feePlans.filter(
        (plan) =>
            plan.feeConfig_id === feeConfigId
    )

    return (
        <TableRow>
            <TableCell
                colSpan={7}
                className="
                    bg-muted/20
                    p-0
                "
            >
                <div className="p-5">

                    {/* header */}
                    <div
                        className="
                            mb-4
                            flex
                            items-center
                            justify-between
                        "
                    >
                        <div>
                            <h3
                                className="
                                    text-sm
                                    font-semibold
                                "
                            >
                                Fee Plans
                            </h3>

                            <p
                                className="
                                    text-xs
                                    text-muted-foreground
                                "
                            >
                                Grade fee structures
                                under this
                                configuration
                            </p>
                        </div>
                    </div>

                    {/* nested table */}
                    <div
                        className="
                            overflow-hidden
                            rounded-2xl
                            border
                            bg-background
                        "
                    >
                        <Table>

                            <TableHeader>
                                <TableRow>

                                    <TableHead>
                                        Grade
                                    </TableHead>

                                    <TableHead>
                                        Plan
                                    </TableHead>

                                    <TableHead>
                                        Q1
                                    </TableHead>

                                    <TableHead>
                                        Q2
                                    </TableHead>

                                    <TableHead>
                                        Q3
                                    </TableHead>

                                    <TableHead>
                                        Q4
                                    </TableHead>

                                    <TableHead>
                                        Total
                                    </TableHead>

                                </TableRow>
                            </TableHeader>

                            <TableBody>

                                {plans.length > 0 ? (
                                    plans.map(
                                        (plan) => {

                                            const total =
                                                plan.first_quarter +
                                                plan.second_quarter +
                                                plan.third_quarter +
                                                plan.fourth_quarter

                                            return (
                                                <TableRow
                                                    key={
                                                        plan.id
                                                    }
                                                >

                                                    {/* grade */}
                                                    <TableCell>
                                                        <Badge
                                                            variant="outline"
                                                            className="rounded-full"
                                                        >
                                                            {
                                                                grade.find(
                                                                    (
                                                                        item
                                                                    ) =>
                                                                        item.id ===
                                                                        plan.grade_id
                                                                )?.name
                                                            }
                                                        </Badge>
                                                    </TableCell>

                                                    {/* name */}
                                                    <TableCell className="font-medium">
                                                        {
                                                            plan.name
                                                        }
                                                    </TableCell>

                                                    {/* q1 */}
                                                    <TableCell>
                                                        {
                                                            plan.first_quarter
                                                        }
                                                    </TableCell>

                                                    {/* q2 */}
                                                    <TableCell>
                                                        {
                                                            plan.second_quarter
                                                        }
                                                    </TableCell>

                                                    {/* q3 */}
                                                    <TableCell>
                                                        {
                                                            plan.third_quarter
                                                        }
                                                    </TableCell>

                                                    {/* q4 */}
                                                    <TableCell>
                                                        {
                                                            plan.fourth_quarter
                                                        }
                                                    </TableCell>

                                                    {/* total */}
                                                    <TableCell>
                                                        <Badge className="rounded-full">
                                                            {
                                                                total
                                                            }
                                                        </Badge>
                                                    </TableCell>
                                                </TableRow>
                                            )
                                        }
                                    )
                                ) : (
                                    <TableRow>
                                        <TableCell
                                            colSpan={7}
                                            className="
                                                h-24
                                                text-center
                                                text-muted-foreground
                                            "
                                        >
                                            No fee plans
                                            found
                                        </TableCell>
                                    </TableRow>
                                )}
                            </TableBody>
                        </Table>
                    </div>
                </div>
            </TableCell>
        </TableRow>
    )
}