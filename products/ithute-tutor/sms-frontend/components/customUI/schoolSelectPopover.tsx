'use client'

import * as React from 'react'

import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'

import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from '@/components/ui/popover'

import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
} from '@/components/ui/command'

import { useAppSelector } from '@/store/hooks'

import { UserRole } from '@/types/shared.primitive'

import {
    ChevronsUpDown,
    Check,
    School,
} from 'lucide-react'

import { cn } from '@/lib/utils'

type SchoolType = {
    id: string
    name: string
}

interface FormProps {
    id: string
    setId: (value: string) => void
}

export function SchoolSelectPopover({
                                        id,
                                        setId,
                                    }: FormProps) {
    const [open, setOpen] = React.useState(false)

    const schools = useAppSelector(
        (state) => state.schools.schools
    ) as SchoolType[]

    const auth = useAppSelector(
        (state) => state.auth.user
    )

    /*
    =========================================
    FILTER SCHOOLS BY ROLE
    =========================================
    */

    const availableSchools =
        auth?.role === UserRole.super_admin
            ? schools
            : schools.filter(
                (school) =>
                    school.id === auth?.school_id
            )

    /*
    =========================================
    AUTO SELECT SINGLE SCHOOL
    =========================================
    */

    React.useEffect(() => {
        if (
            availableSchools.length === 1 &&
            !id
        ) {
            setId(availableSchools[0].id)
        }
    }, [availableSchools, id, setId])

    const selectedSchool =
        availableSchools.find(
            (school) => school.id === id
        )

    const disabled =
        availableSchools.length <= 1


    return (
        <div className="space-y-2">
            <Label className="text-sm font-semibold">
                School
            </Label>

            <Popover
                open={disabled ? false : open}
                onOpenChange={setOpen}
            >
                <PopoverTrigger asChild>
                    <Button
                        variant="outline"
                        role="combobox"
                        disabled={disabled}
                        className={cn(
                            'h-12 w-full justify-between rounded-2xl border-0 bg-muted/50 px-4 shadow-sm',
                            !selectedSchool &&
                            'text-muted-foreground'
                        )}
                    >
                        <div className="flex items-center gap-3 truncate">
                            <School className="h-4 w-4 shrink-0 text-muted-foreground" />

                            <span className="truncate">
                                {selectedSchool
                                    ? selectedSchool.name
                                    : 'Select school'}
                            </span>
                        </div>

                        {!disabled && (
                            <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />
                        )}
                    </Button>
                </PopoverTrigger>

                <PopoverContent
                    align="start"
                    className="
                        w-(--radix-popover-trigger-width)
                        rounded-2xl
                        border-0
                        p-0
                        shadow-xl
                    "
                >
                    <Command>
                        <CommandInput placeholder="Search school..." />

                        <CommandList>
                            <CommandEmpty>
                                No school found.
                            </CommandEmpty>

                            <CommandGroup>
                                {availableSchools.map(
                                    (school) => (
                                        <CommandItem
                                            key={school.id}
                                            value={school.name}
                                            onSelect={() => {
                                                setId(
                                                    school.id
                                                )

                                                setOpen(
                                                    false
                                                )
                                            }}
                                            className="cursor-pointer"
                                        >
                                            <Check
                                                className={cn(
                                                    'mr-2 h-4 w-4',
                                                    id ===
                                                    school.id
                                                        ? 'opacity-100'
                                                        : 'opacity-0'
                                                )}
                                            />

                                            {school.name}
                                        </CommandItem>
                                    )
                                )}
                            </CommandGroup>
                        </CommandList>
                    </Command>
                </PopoverContent>
            </Popover>
        </div>
    )
}