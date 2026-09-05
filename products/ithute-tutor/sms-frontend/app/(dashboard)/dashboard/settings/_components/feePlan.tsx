'use client'

import * as React from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import {
    Dialog,
    DialogContent,
    DialogFooter,
} from '@/components/ui/dialog'

import { useAppDispatch, useAppSelector } from '@/store/hooks'

import {
    FeePlanCreate,
    FeePlanRead,
    FeePlanUpdate,
} from '@/types/finance/feePlan'

import {
    createFeePlanThunk,
    updateFeePlanThunk,
} from '@/store/features/thunks/finance/feePlan'

import { ToolboxIcon } from 'lucide-react'

import { DialogHeroHeader } from '@/components/customUI/dialogHeader'
import { GradeSelectPopover } from '@/components/customUI/gradeSelectPopover'

/* =========================================
   PROPS
========================================= */

interface Props {
    open: boolean

    onOpenChange: (open: boolean) => void

    feeConfigId: string

    mode: 'create' | 'edit'

    initialData?: FeePlanRead
}

/* =========================================
   FORM TYPE
========================================= */

type FeePlanFormState =
    Omit<FeePlanCreate, 'feeConfig_id'>

/* =========================================
   COMPONENT
========================================= */

export function FeePlanDialog({
                                  open,
                                  onOpenChange,
                                  feeConfigId,
                                  mode,
                                  initialData,
                              }: Props) {
    const dispatch = useAppDispatch()

    const { loading } = useAppSelector(
        (state) => state.feePlan
    )

    /* =========================================
       INITIAL VALUES
    ========================================= */

    const initialFormValues =
        React.useMemo<FeePlanFormState>(
            () => ({
                grade_id:
                    initialData?.grade_id ?? '',

                name:
                    initialData?.name ?? '',

                first_quarter:
                    initialData?.first_quarter ?? 0,

                second_quarter:
                    initialData?.second_quarter ?? 0,

                third_quarter:
                    initialData?.third_quarter ?? 0,

                fourth_quarter:
                    initialData?.fourth_quarter ?? 0,

                description:
                    initialData?.description ?? '',
            }),
            [initialData]
        )

    /* =========================================
       STATE
    ========================================= */

    const [form, setForm] =
        React.useState<FeePlanFormState>(
            initialFormValues
        )

    /* =========================================
       HANDLE OPEN CHANGE
    ========================================= */

    const handleOpenChange = (
        value: boolean
    ) => {
        if (value) {
            setForm(initialFormValues)
        }

        onOpenChange(value)
    }

    /* =========================================
       FIELD UPDATER
    ========================================= */

    const setField = <
        K extends keyof FeePlanFormState
    >(
        key: K,
        value: FeePlanFormState[K]
    ) => {
        setForm((prev) => ({
            ...prev,
            [key]: value,
        }))
    }

    /* =========================================
       SUBMIT
    ========================================= */

    const handleSubmit = async () => {
        try {
            if (mode === 'create') {
                const payload: FeePlanCreate = {
                    ...form,
                    feeConfig_id: feeConfigId,
                }

                await dispatch(
                    createFeePlanThunk(payload)
                ).unwrap()
            }

            else if (initialData) {
                const payload: FeePlanUpdate = {
                    grade_id:
                    form.grade_id,

                    name:
                    form.name,

                    first_quarter:
                    form.first_quarter,

                    second_quarter:
                    form.second_quarter,

                    third_quarter:
                    form.third_quarter,

                    fourth_quarter:
                    form.fourth_quarter,

                    description:
                    form.description,
                }

                await dispatch(
                    updateFeePlanThunk({
                        id: initialData.id,
                        payload,
                    })
                ).unwrap()
            }

            onOpenChange(false)
        }

        catch (error) {
            console.error(error)
        }
    }

    /* =========================================
       UI
    ========================================= */

    return (
        <Dialog
            open={open}
            onOpenChange={handleOpenChange}
        >
            <DialogContent
                className="
                    sm:max-w-3xl
                    overflow-hidden
                    rounded-[2rem]
                    border-0
                    p-0
                "
            >
                <DialogHeroHeader
                    title={
                        mode === 'create'
                            ? 'Create Fee Plan'
                            : 'Edit Fee Plan'
                    }
                    description="
                        Configure fee structures,
                        grade billing plans,
                        and quarterly payment allocations.
                    "
                    icon={
                        <ToolboxIcon className="h-8 w-8" />
                    }
                />

                {/* BODY */}
                <div className="space-y-8 p-8">

                    {/* NAME + GRADE */}
                    <div className="grid gap-6 md:grid-cols-2">

                        <div className="space-y-3">
                            <Label className="text-sm font-semibold">
                                Plan Name
                            </Label>

                            <Input
                                value={form.name}
                                onChange={(e) =>
                                    setField(
                                        'name',
                                        e.target.value
                                    )
                                }
                                placeholder="
                                    e.g. Grade 7 Standard Plan
                                "
                                className="
                                    h-12
                                    rounded-2xl
                                    border-0
                                    bg-muted/50
                                    shadow-sm
                                "
                            />
                        </div>

                        <GradeSelectPopover
                            value={form.grade_id}
                            onChange={(value) =>
                                setField(
                                    'grade_id',
                                    value
                                )
                            }
                        />
                    </div>

                    {/* QUARTERS */}
                    <div className="grid gap-5 md:grid-cols-2">

                        <div className="space-y-3">
                            <Label className="text-sm font-semibold">
                                First Quarter
                            </Label>

                            <Input
                                type="number"
                                value={
                                    form.first_quarter
                                }
                                onChange={(e) =>
                                    setField(
                                        'first_quarter',
                                        Number(
                                            e.target.value
                                        )
                                    )
                                }
                                className="
                                    h-12
                                    rounded-2xl
                                    border-0
                                    bg-muted/50
                                    shadow-sm
                                "
                            />
                        </div>

                        <div className="space-y-3">
                            <Label className="text-sm font-semibold">
                                Second Quarter
                            </Label>

                            <Input
                                type="number"
                                value={
                                    form.second_quarter
                                }
                                onChange={(e) =>
                                    setField(
                                        'second_quarter',
                                        Number(
                                            e.target.value
                                        )
                                    )
                                }
                                className="
                                    h-12
                                    rounded-2xl
                                    border-0
                                    bg-muted/50
                                    shadow-sm
                                "
                            />
                        </div>

                        <div className="space-y-3">
                            <Label className="text-sm font-semibold">
                                Third Quarter
                            </Label>

                            <Input
                                type="number"
                                value={
                                    form.third_quarter
                                }
                                onChange={(e) =>
                                    setField(
                                        'third_quarter',
                                        Number(
                                            e.target.value
                                        )
                                    )
                                }
                                className="
                                    h-12
                                    rounded-2xl
                                    border-0
                                    bg-muted/50
                                    shadow-sm
                                "
                            />
                        </div>

                        <div className="space-y-3">
                            <Label className="text-sm font-semibold">
                                Fourth Quarter
                            </Label>

                            <Input
                                type="number"
                                value={
                                    form.fourth_quarter
                                }
                                onChange={(e) =>
                                    setField(
                                        'fourth_quarter',
                                        Number(
                                            e.target.value
                                        )
                                    )
                                }
                                className="
                                    h-12
                                    rounded-2xl
                                    border-0
                                    bg-muted/50
                                    shadow-sm
                                "
                            />
                        </div>
                    </div>

                    {/* DESCRIPTION */}
                    <div className="space-y-3">
                        <Label className="text-sm font-semibold">
                            Description
                        </Label>

                        <Input
                            value={
                                form.description ?? ''
                            }
                            onChange={(e) =>
                                setField(
                                    'description',
                                    e.target.value
                                )
                            }
                            placeholder="
                                Additional notes about this fee plan
                            "
                            className="
                                h-12
                                rounded-2xl
                                border-0
                                bg-muted/50
                                shadow-sm
                            "
                        />
                    </div>
                </div>

                {/* FOOTER */}
                <DialogFooter
                    className="
                        border-t
                        bg-muted/20
                        px-8
                        py-5
                    "
                >
                    <Button
                        onClick={handleSubmit}
                        disabled={loading}
                        className="
                            h-12
                            w-full
                            rounded-2xl
                        "
                    >
                        {mode === 'create'
                            ? 'Create Fee Plan'
                            : 'Update Fee Plan'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}