// components/ui/dialog-hero-header.tsx

'use client'

import * as React from 'react'

import {
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'

import { cn } from '@/lib/utils'

interface DialogHeroHeaderProps
    extends React.HTMLAttributes<HTMLDivElement> {
    title: string
    description?: string
    icon?: React.ReactNode
    image?: string
}

export function DialogHeroHeader({
                                     title,
                                     description,
                                     icon,
                                     image = '/burner.png',
                                     className,
                                     children,
                                     ...props
                                 }: DialogHeroHeaderProps) {
    return (
        <div
            className={cn(
                'relative isolate overflow-hidden border-b',
                className
            )}
            {...props}
        >
            {/* BACKGROUND IMAGE */}
            <div
                className="
                    absolute inset-0
                    bg-cover bg-center
                    opacity-15
                    pointer-events-none
                "
                style={{
                    backgroundImage: `url(${image})`,
                }}
            />

            {/* GRADIENT OVERLAY */}
            <div
                className="
                    absolute inset-0
                    bg-gradient-to-br
                    from-primary/20
                    via-background/95
                    to-primary/10
                    backdrop-blur-[2px]
                    pointer-events-none
                "
            />

            {/* GLOW */}
            <div
                className="
                    absolute -right-20 -top-20
                    h-60 w-60 rounded-full
                    bg-primary/10 blur-3xl
                    pointer-events-none
                "
            />

            {/* CONTENT */}
            <DialogHeader className="relative z-10 p-8">
                {icon && (
                    <div
                        className="
                            mb-5 flex h-16 w-16
                            items-center justify-center
                            rounded-3xl
                            bg-primary
                            text-primary-foreground
                            shadow-xl
                            ring-4 ring-primary/10
                        "
                    >
                        {icon}
                    </div>
                )}

                <DialogTitle className="text-3xl font-bold tracking-tight">
                    {title}
                </DialogTitle>

                {description && (
                    <DialogDescription
                        className="
                            max-w-xl
                            pt-2
                            text-base
                            leading-relaxed
                            text-muted-foreground
                        "
                    >
                        {description}
                    </DialogDescription>
                )}

                {children}
            </DialogHeader>
        </div>
    )
}