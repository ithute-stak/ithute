'use client'

import * as React from 'react'

import { useAppDispatch, useAppSelector } from '@/store/hooks'
import { SchoolFeeConfigurationRead } from '@/types/finance/schoolFeeConfiguration'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Plus } from 'lucide-react'

import {
    deleteSchoolFeeConfigurationThunk,
    fetchSchoolFeeConfigurations,
} from '@/store/features/thunks/finance/schoolFeeConfiguration/schoolFeeConfigurationThunk'

import { SchoolFeeConfigurationForm } from '@/app/(dashboard)/dashboard/settings/_components/schoolFeeConfigurationsForm'
import { FeeKpiCards } from '@/app/(dashboard)/dashboard/settings/_components/feeKPICard'
import { FeeConfigTable } from '@/app/(dashboard)/dashboard/settings/_components/feeConfigTable'
import {FeePlanDialog} from "@/app/(dashboard)/dashboard/settings/_components/feePlan";
import {useAppData} from "@/provider/dataProvider";


export default function SchoolFeeConfigurationPage() {
    const dispatch = useAppDispatch()

    const {
        schoolFeeConfigs
    } = useAppData()

    const [createOpen, setCreateOpen] = React.useState(false)
    const [editOpen, setEditOpen] = React.useState(false)

    const [planOpen, setPlanOpen] = React.useState(false)
    const [selectedFeeConfigId, setSelectedFeeConfigId] = React.useState('')

    const [selected, setSelected] =
        React.useState<SchoolFeeConfigurationRead | null>(null)

    React.useEffect(() => {
        dispatch(fetchSchoolFeeConfigurations())
    }, [dispatch])

    const handleEdit = (item: SchoolFeeConfigurationRead) => {
        setSelected(item)
        setEditOpen(true)
    }

    const handleDelete = async (item: SchoolFeeConfigurationRead) => {
        await dispatch(deleteSchoolFeeConfigurationThunk(item.id))
        await dispatch(fetchSchoolFeeConfigurations())
    }

    const handleAddPlan = (item: SchoolFeeConfigurationRead) => {
        setSelectedFeeConfigId(item.id)
        setPlanOpen(true)
    }

    return (
        <div className="space-y-10 p-6">

            {/* HERO */}
            <div className="relative overflow-hidden rounded-3xl border bg-muted/20 p-8">

                <div
                    className="absolute inset-0 bg-cover bg-center opacity-10"
                    style={{ backgroundImage: "url('/burner.png')" }}
                />

                <div className="absolute inset-0 bg-linear-to-r from-background via-background/80 to-background/60" />

                <div className="relative flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">

                    <div className="space-y-2">
                        <Badge className="rounded-full px-4 py-1 text-xs">
                            Finance Management
                        </Badge>

                        <h1 className="text-4xl font-bold tracking-tight">
                            School Fee Configuration
                        </h1>

                        <p className="max-w-2xl text-muted-foreground">
                            Manage academic years, billing structures, and payment policies.
                        </p>
                    </div>

                    <Button
                        onClick={() => setCreateOpen(true)}
                        className="h-11 rounded-2xl px-6 shadow-sm"
                    >
                        <Plus className="mr-2 h-4 w-4" />
                        New Configuration
                    </Button>
                </div>
            </div>

            {/* KPI */}
            <FeeKpiCards configurations={schoolFeeConfigs} />

            {/* TABLE */}
            <Card className="rounded-2xl border-0 shadow-sm p-3">
                <CardContent className="p-0">
                    <FeeConfigTable
                        configurations={schoolFeeConfigs}
                        onEdit={handleEdit}
                        onDelete={handleDelete}
                        onAddPlan={handleAddPlan}
                    />
                </CardContent>
            </Card>

            {/* CONFIG FORM */}
            <SchoolFeeConfigurationForm
                open={createOpen}
                onOpenChange={setCreateOpen}
                mode="create"
            />

            {selected && (
                <SchoolFeeConfigurationForm
                    open={editOpen}
                    onOpenChange={(open) => {
                        setEditOpen(open)
                        if (!open) setSelected(null)
                    }}
                    mode="edit"
                    initialData={selected}
                />
            )}

            {/* ✅ FEE PLAN DIALOG (NEW) */}
            <FeePlanDialog
                open={planOpen}
                onOpenChange={setPlanOpen}
                feeConfigId={selectedFeeConfigId}
                mode="create"
            />
        </div>
    )
}