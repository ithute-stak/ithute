// components/school-fee/FeeConfigActions.tsx

'use client'

import { Button } from '@/components/ui/button'
import { Pencil, Trash2, BookPlus } from 'lucide-react'
import { SchoolFeeConfigurationRead } from '@/types/finance/schoolFeeConfiguration'

interface Props {
    item: SchoolFeeConfigurationRead
    onEdit: (item: SchoolFeeConfigurationRead) => void
    onDelete: (item: SchoolFeeConfigurationRead) => void
    onAddPlan: (item: SchoolFeeConfigurationRead) => void
}

export function FeeConfigActions({item, onEdit, onDelete, onAddPlan}: Props) {
    return (
        <div className="flex justify-end gap-2">
            {/* ADD PLAN */}
            <Button
                size="icon"
                variant="outline"
                className="rounded-2xl"
                onClick={() => onAddPlan(item)}
            >
                <BookPlus className="h-4 w-4" />
            </Button>

            {/* EDIT */}
            <Button
                size="icon"
                variant="outline"
                className="rounded-2xl"
                onClick={() => onEdit(item)}
            >
                <Pencil className="h-4 w-4" />
            </Button>

            {/* DELETE */}
            <Button
                size="icon"
                variant="destructive"
                className="rounded-2xl"
                onClick={() => onDelete(item)}
            >
                <Trash2 className="h-4 w-4" />
            </Button>
        </div>
    )
}