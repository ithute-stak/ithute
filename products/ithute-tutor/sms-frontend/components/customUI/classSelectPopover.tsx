// components/customUI/class-select-popover.tsx

'use client'

import * as React from 'react'

import { Check, ChevronsUpDown, GraduationCap } from 'lucide-react'

import { cn } from '@/lib/utils'

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

type ClassType = {
    id: string
    name: string
}

interface ClassSelectPopoverProps {
    label?: string

    placeholder?: string

    searchPlaceholder?: string

    emptyMessage?: string

    value: string

    onChange: (value: string) => void

    classes: ClassType[]

    disabled?: boolean
}

export function ClassSelectPopover({
                                       label = 'Class',

                                       placeholder = 'Select class',

                                       searchPlaceholder = 'Search class...',

                                       emptyMessage = 'No class found.',

                                       value,

                                       onChange,

                                       classes,

                                       disabled = false,
                                   }: ClassSelectPopoverProps) {
    const [open, setOpen] = React.useState(false)

    const selectedClass = classes.find(
        (currentClass) =>
            currentClass.id === value
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
                            !selectedClass &&
                            'text-muted-foreground'
                        )}
                    >
                        <div className="flex items-center gap-3 truncate">
                            <GraduationCap className="h-4 w-4 shrink-0 text-muted-foreground" />

                            <span className="truncate">
                                {selectedClass
                                    ? selectedClass.name
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
                                {classes.map(
                                    (currentClass) => (
                                        <CommandItem
                                            key={
                                                currentClass.id
                                            }
                                            value={
                                                currentClass.name
                                            }
                                            onSelect={() => {
                                                onChange(
                                                    currentClass.id
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
                                                    value ===
                                                    currentClass.id
                                                        ? 'opacity-100'
                                                        : 'opacity-0'
                                                )}
                                            />

                                            {
                                                currentClass.name
                                            }
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