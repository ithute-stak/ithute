import {useAppDispatch, useAppSelector} from "@/store/hooks";
import {
    SchoolFeeConfigurationCreate,
    SchoolFeeConfigurationRead,
    SchoolFeeConfigurationUpdate
} from "@/types/finance/schoolFeeConfiguration";
import * as React from "react";
import {
    createSchoolFeeConfigurationThunk,
    fetchSchoolFeeConfigurations, updateSchoolFeeConfigurationThunk
} from "@/store/features/thunks/finance/schoolFeeConfiguration/schoolFeeConfigurationThunk";
import {
    Dialog,
    DialogContent,
    DialogFooter,
} from "@/components/ui/dialog";
import {Button} from "@/components/ui/button";
import {AlertCircle, CalendarDays, CheckCircle2, Loader2, School, Wallet} from "lucide-react";
import {format} from "date-fns";
import {Label} from "@/components/ui/label";
import {Select, SelectContent, SelectItem, SelectTrigger, SelectValue} from "@/components/ui/select";
import {Popover, PopoverContent, PopoverTrigger} from "@/components/ui/popover";
import {Calendar} from "@/components/ui/calendar";
import {cn} from "@/lib/utils";
import {Switch} from "@/components/ui/switch";
import {DialogHeroHeader} from "@/components/customUI/dialogHeader";
import {SchoolSelectPopover} from "@/components/customUI/schoolSelectPopover";

const feeStructureOptions = [
    {
        value: 'quarterly',
        label: 'Quarterly',
    },
    {
        value: 'monthly',
        label: 'Monthly',
    },
    {
        value: 'annual',
        label: 'Annual',
    },
]

interface FormProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    mode: 'create' | 'edit'
    initialData?: SchoolFeeConfigurationRead
}

export function SchoolFeeConfigurationForm({open, onOpenChange, mode, initialData}: FormProps) {
    const dispatch = useAppDispatch()

    const {loading} = useAppSelector(
        (state) => state.schoolFeeConfiguration
    )

    /*
    =========================================
    INITIAL VALUES
    =========================================
    */
    const initialFormValues = React.useMemo<SchoolFeeConfigurationCreate>(
        () => ({
            school_id: initialData?.school_id ?? '',
            year_start: initialData?.year_start ?? '',
            year_end: initialData?.year_end ?? '',
            fee_structure:
                initialData?.fee_structure ?? 'quarterly',
            allow_partial_payments:
                initialData?.allow_partial_payments ?? true,
            allow_late_payments:
                initialData?.allow_late_payments ?? true,
        }),
        [initialData]
    )

    const [form, setForm] =
        React.useState<SchoolFeeConfigurationCreate>(
            initialFormValues
        )

    const [yearStart, setYearStart] =
        React.useState<Date | undefined>(
            initialData?.year_start
                ? new Date(initialData.year_start)
                : undefined
        )

    const [yearEnd, setYearEnd] =
        React.useState<Date | undefined>(
            initialData?.year_end
                ? new Date(initialData.year_end)
                : undefined
        )

    const handleOpenChange = (value: boolean) => {
        if (!value) {
            setForm(initialFormValues)

            setYearStart(
                initialData?.year_start
                    ? new Date(initialData.year_start)
                    : undefined
            )

            setYearEnd(
                initialData?.year_end
                    ? new Date(initialData.year_end)
                    : undefined
            )
        }

        onOpenChange(value)
    }

    /*
    =========================================
    SUBMIT
    =========================================
    */

    async function handleSubmit() {
        if (!yearStart || !yearEnd) return

        const payload = {
            ...form,
            year_start: format(yearStart, 'yyyy-MM-dd'),
            year_end: format(yearEnd, 'yyyy-MM-dd'),
        }

        try {
            if (mode === 'create') {
                await dispatch(
                    createSchoolFeeConfigurationThunk(payload)
                ).unwrap()
            } else if (initialData) {
                await dispatch(
                    updateSchoolFeeConfigurationThunk({
                        id: initialData.id,
                        payload:
                            payload as SchoolFeeConfigurationUpdate,
                    })
                ).unwrap()
            }

            await dispatch(fetchSchoolFeeConfigurations())

            onOpenChange(false)
        } catch (error) {
            console.error(error)
        }
    }

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="sm:max-w-3xl overflow-hidden rounded-4xl border-0 p-0">
                <DialogHeroHeader
                    title="Create Fee Configuration"
                    description="Configure academic years, fee structures, and payment policies for your school system."
                    icon={<Wallet className="h-8 w-8" />}
                />

                {/* BODY */}
                <div className="space-y-8 p-8">
                    {/* SCHOOL + STRUCTURE */}
                    <div className="grid gap-6 md:grid-cols-2">
                        <SchoolSelectPopover
                            id={form.school_id}
                            setId={(schoolId: string) =>
                                setForm((prev) => ({
                                    ...prev,
                                    school_id: schoolId,
                                }))
                            }
                        />
                        <div className="space-y-3">
                            <Label className="text-sm font-semibold">
                                Fee Structure
                            </Label>

                            <Select
                                value={form.fee_structure}
                                onValueChange={(value) =>
                                    setForm((prev) => ({
                                        ...prev,
                                        fee_structure:
                                            value as
                                                | 'quarterly'
                                                | 'monthly'
                                                | 'annual',
                                    }))
                                }
                            >
                                <SelectTrigger className="h-12 rounded-2xl border-0 bg-muted/50 shadow-sm">
                                    <SelectValue placeholder="Select structure"/>
                                </SelectTrigger>

                                <SelectContent className="rounded-2xl">
                                    {feeStructureOptions.map(
                                        (option) => (
                                            <SelectItem
                                                key={option.value}
                                                value={
                                                    option.value
                                                }
                                                className="rounded-xl"
                                            >
                                                {option.label}
                                            </SelectItem>
                                        )
                                    )}
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    {/* DATES */}
                    <div className="grid gap-6 md:grid-cols-2">
                        <div className="space-y-3">
                            <Label className="text-sm font-semibold">
                                Academic Year Start
                            </Label>

                            <Popover>
                                <PopoverTrigger asChild>
                                    <Button
                                        variant="outline"
                                        className={cn(
                                            'h-12 w-full justify-start rounded-2xl border-0 bg-muted/50 text-left font-normal shadow-sm',
                                            !yearStart &&
                                            'text-muted-foreground'
                                        )}
                                    >
                                        <CalendarDays className="mr-3 h-4 w-4"/>

                                        {yearStart ? (
                                            format(
                                                yearStart,
                                                'PPP'
                                            )
                                        ) : (
                                            <span>
                                                Select year
                                                start
                                            </span>
                                        )}
                                    </Button>
                                </PopoverTrigger>

                                <PopoverContent className="w-auto overflow-hidden rounded-3xl border-0 p-0 shadow-xl">
                                    <Calendar
                                        mode="single"
                                        selected={yearStart}
                                        onSelect={setYearStart}
                                        required={false}
                                    />
                                </PopoverContent>
                            </Popover>
                        </div>

                        <div className="space-y-3">
                            <Label className="text-sm font-semibold">
                                Academic Year End
                            </Label>

                            <Popover>
                                <PopoverTrigger asChild>
                                    <Button
                                        variant="outline"
                                        className={cn(
                                            'h-12 w-full justify-start rounded-2xl border-0 bg-muted/50 text-left font-normal shadow-sm',
                                            !yearEnd &&
                                            'text-muted-foreground'
                                        )}
                                    >
                                        <CalendarDays className="mr-3 h-4 w-4"/>

                                        {yearEnd ? (
                                            format(
                                                yearEnd,
                                                'PPP'
                                            )
                                        ) : (
                                            <span>
                                                Select year end
                                            </span>
                                        )}
                                    </Button>
                                </PopoverTrigger>

                                <PopoverContent className="w-auto overflow-hidden rounded-3xl border-0 p-0 shadow-xl">
                                    <Calendar
                                        mode="single"
                                        selected={yearEnd}
                                        onSelect={setYearEnd}
                                        required={false}
                                    />
                                </PopoverContent>
                            </Popover>
                        </div>
                    </div>

                    {/* SWITCHES */}
                    <div className="grid gap-5 md:grid-cols-2">
                        <div className="flex items-center justify-between rounded-3xl border bg-muted/30 p-5">
                            <div className="space-y-1">
                                <div className="flex items-center gap-2">
                                    <CheckCircle2 className="h-5 w-5 text-primary"/>

                                    <p className="font-semibold">
                                        Partial Payments
                                    </p>
                                </div>

                                <p className="text-sm text-muted-foreground">
                                    Allow students to pay in
                                    smaller installments.
                                </p>
                            </div>

                            <Switch
                                checked={
                                    form.allow_partial_payments
                                }
                                onCheckedChange={(checked) =>
                                    setForm((prev) => ({
                                        ...prev,
                                        allow_partial_payments:
                                        checked,
                                    }))
                                }
                            />
                        </div>

                        <div className="flex items-center justify-between rounded-3xl border bg-muted/30 p-5">
                            <div className="space-y-1">
                                <div className="flex items-center gap-2">
                                    <AlertCircle className="h-5 w-5 text-primary"/>

                                    <p className="font-semibold">
                                        Late Payments
                                    </p>
                                </div>

                                <p className="text-sm text-muted-foreground">
                                    Allow fee payments after
                                    due dates.
                                </p>
                            </div>

                            <Switch
                                checked={
                                    form.allow_late_payments
                                }
                                onCheckedChange={(checked) =>
                                    setForm((prev) => ({
                                        ...prev,
                                        allow_late_payments:
                                        checked,
                                    }))
                                }
                            />
                        </div>
                    </div>
                </div>

                {/* FOOTER */}
                <DialogFooter className="border-t bg-muted/20 px-8 py-5">
                    <Button
                        onClick={handleSubmit}
                        disabled={loading}
                        className="h-12 rounded-2xl px-8 w-full mb-5"
                    >
                        {loading ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin"/>
                                Saving...
                            </>
                        ) : mode === 'create' ? (
                            'Create Configuration'
                        ) : (
                            'Update Configuration'
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}