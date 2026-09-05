// components/customUI/grade-select-popover.tsx

'use client'

import * as React from 'react'

import {
    Check,
    ChevronsUpDown,
    BookOpen,
} from 'lucide-react'

import { cn } from '@/lib/utils'

import { useAppData } from '@/provider/dataProvider'

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

type GradeType = {
    id: string
    name: string
}

interface GradeSelectPopoverProps {
    label?: string

    placeholder?: string

    searchPlaceholder?: string

    emptyMessage?: string

    value: string

    onChange: (value: string) => void

    disabled?: boolean
}

export function GradeSelectPopover({
                                       label = 'Grade',

                                       placeholder = 'Select grade',

                                       searchPlaceholder = 'Search grade...',

                                       emptyMessage = 'No grade found.',

                                       value,

                                       onChange,

                                       disabled = false,
                                   }: GradeSelectPopoverProps) {
    const [open, setOpen] = React.useState(false)

    const { grade} = useAppData()

    const selectedGrade = grade.find(
        (g) => g.id === value
    )

    return (
        <div className="space-y-3">
            <Label className="text-sm font-semibold">
                {label}
            </Label>

            <Popover
                open={disabled ? false : open}
                onOpenChange={setOpen}
            >
                <PopoverTrigger asChild>
                    <Button
                        type="button"
                        variant="outline"
                        role="combobox"
                        disabled={disabled}
                        className={cn(
                            `
                            h-12 w-full
                            justify-between
                            rounded-2xl
                            border-0
                            bg-muted/50
                            px-4
                            shadow-sm
                            `,
                            !selectedGrade &&
                            'text-muted-foreground'
                        )}
                    >
                        <div className="flex items-center gap-3 truncate">
                            <BookOpen className="h-4 w-4 shrink-0 text-muted-foreground" />

                            <span className="truncate">
                                {selectedGrade
                                    ? selectedGrade.name
                                    : placeholder}
                            </span>
                        </div>

                        <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />
                    </Button>
                </PopoverTrigger>

                <PopoverContent
                    align="start"
                    className="
                        w-[var(--radix-popover-trigger-width)]
                        rounded-2xl
                        border-0
                        p-0
                        shadow-xl
                    "
                >
                    <Command>
                        <CommandInput
                            placeholder={
                                searchPlaceholder
                            }
                        />

                        <CommandList>
                            <CommandEmpty>
                                {emptyMessage}
                            </CommandEmpty>

                            <CommandGroup>
                                {grade.map((g) => (
                                    <CommandItem
                                        key={g.id}
                                        value={g.name}
                                        onSelect={() => {
                                            onChange(
                                                g.id
                                            )

                                            setOpen(false)
                                        }}
                                        className="cursor-pointer"
                                    >
                                        <Check
                                            className={cn(
                                                'mr-2 h-4 w-4',
                                                value ===
                                                g.id
                                                    ? 'opacity-100'
                                                    : 'opacity-0'
                                            )}
                                        />

                                        {g.name}
                                    </CommandItem>
                                ))}
                            </CommandGroup>
                        </CommandList>
                    </Command>
                </PopoverContent>
            </Popover>
        </div>
    )
}