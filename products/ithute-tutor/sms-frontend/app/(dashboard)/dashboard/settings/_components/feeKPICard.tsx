// components/school-fee/FeeKpiCards.tsx

'use client'

import { Card, CardContent } from '@/components/ui/card'
import { Wallet, CalendarDays, CheckCircle2 } from 'lucide-react'
import { SchoolFeeConfigurationRead } from '@/types/finance/schoolFeeConfiguration'

interface Props {
    configurations: SchoolFeeConfigurationRead[]
}

export function FeeKpiCards({ configurations }: Props) {
    const total = configurations.length

    const quarterly = configurations.filter(
        (c) => c.fee_structure === 'quarterly'
    ).length

    const active = configurations.filter(
        (c) => c.allow_late_payments
    ).length

    return (
        <div className="grid gap-5 md:grid-cols-3">
            <Card className="rounded-3xl border-0 shadow-sm">
                <CardContent className="flex justify-between p-6">
                    <div>
                        <p className="text-sm text-muted-foreground">
                            Total Configurations
                        </p>
                        <h2 className="text-4xl font-bold">{total}</h2>
                    </div>
                    <Wallet className="h-7 w-7 text-primary" />
                </CardContent>
            </Card>

            <Card className="rounded-3xl border-0 shadow-sm">
                <CardContent className="flex justify-between p-6">
                    <div>
                        <p className="text-sm text-muted-foreground">
                            Quarterly Structures
                        </p>
                        <h2 className="text-4xl font-bold">{quarterly}</h2>
                    </div>
                    <CalendarDays className="h-7 w-7 text-primary" />
                </CardContent>
            </Card>

            <Card className="rounded-3xl border-0 shadow-sm">
                <CardContent className="flex justify-between p-6">
                    <div>
                        <p className="text-sm text-muted-foreground">
                            Active Policies
                        </p>
                        <h2 className="text-4xl font-bold">{active}</h2>
                    </div>
                    <CheckCircle2 className="h-7 w-7 text-primary" />
                </CardContent>
            </Card>
        </div>
    )
}