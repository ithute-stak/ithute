"use client"

import { usePathname } from "next/navigation"
import Link from "next/link"

import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"

import { Bell, Building2, Check, ChevronsUpDown } from "lucide-react"
import { Button } from "@/components/ui/button"

import { UserDropdown } from "@/app/(visitors)/_components/user_drop_down"
import { ThemeToggle } from "@/components/ui/theme-toggle"

import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

import { useNotifications } from "@/provider/notification_provider"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"

export function SiteHeader() {
    const pathname = usePathname()
    const {
        workspace,
        memberships,
        loading: schoolLoading,
        hasMultipleSchools,
        switchSchool,
    } = useSchoolWorkspace()

    const {
        notifications,
        unreadCount,
        markAllAsRead,
        clearNotifications,
    } = useNotifications()

    const getBreadcrumbs = (path: string) => {
        const segments = path.split("/").filter(Boolean)

        return segments.map((segment, index) => {
            const href = "/" + segments.slice(0, index + 1).join("/")

            const label = segment
                .replace("-", " ")
                .replace(/\b\w/g, (c) => c.toUpperCase())

            return {
                label,
                href,
                isLast: index === segments.length - 1,
            }
        })
    }

    const schoolIdentity = (
        <div className="flex max-w-[280px] items-center gap-2 rounded-md border bg-background px-2.5 py-1.5">
            {workspace?.school.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                    src={workspace.school.logo_url}
                    alt=""
                    className="h-7 w-7 shrink-0 rounded-md border object-cover"
                />
            ) : (
                <div
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border text-xs font-bold"
                    style={workspace?.school.primary_color ? {
                        backgroundColor: workspace.school.primary_color,
                        color: "white",
                    } : undefined}
                >
                    {workspace?.school.name?.slice(0, 1).toUpperCase() ?? <Building2 className="h-4 w-4" />}
                </div>
            )}
            <div className="min-w-0 text-left leading-tight">
                <div className="truncate text-sm font-semibold">
                    {workspace?.school.name ?? (schoolLoading ? "Loading school…" : "School workspace")}
                </div>
                {workspace && (
                    <div className="truncate text-[10px] capitalize text-muted-foreground">
                        {workspace.role.replaceAll("_", " ")}
                    </div>
                )}
            </div>
        </div>
    )

    return (
        <header className="flex h-(--header-height) shrink-0 items-center justify-between border-b px-4 lg:px-6">
            <div className="flex min-w-0 items-center gap-2">
                <SidebarTrigger className="-ml-1" />

                <Separator orientation="vertical" className="mx-2 h-4" />

                <div className="hidden items-center gap-1 text-sm font-medium lg:flex">
                    {pathname === "/" ? (
                        <span>Home</span>
                    ) : (
                        getBreadcrumbs(pathname).map((item) => (
                            <div key={item.href} className="flex items-center gap-1">
                                {!item.isLast ? (
                                    <Link
                                        href={item.href}
                                        className="text-muted-foreground transition-colors hover:text-foreground"
                                    >
                                        {item.label}
                                    </Link>
                                ) : (
                                    <span className="text-foreground">
                                        {item.label}
                                    </span>
                                )}

                                {!item.isLast && (
                                    <span className="text-muted-foreground">/</span>
                                )}
                            </div>
                        ))
                    )}
                </div>
            </div>

            <div className="flex items-center gap-2 lg:gap-3">
                {hasMultipleSchools ? (
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <button
                                type="button"
                                className="group flex items-center gap-1 rounded-md outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring"
                                disabled={schoolLoading}
                                aria-label="Switch school workspace"
                            >
                                {schoolIdentity}
                                <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground" />
                            </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-80">
                            <DropdownMenuLabel>
                                <div className="flex flex-col gap-0.5">
                                    <span>Switch school</span>
                                    <span className="text-xs font-normal text-muted-foreground">
                                        Each school opens as its own private workspace.
                                    </span>
                                </div>
                            </DropdownMenuLabel>
                            <DropdownMenuSeparator />

                            {memberships.map((membership) => {
                                const active = workspace?.school.id === membership.school_id
                                return (
                                    <DropdownMenuItem
                                        key={`${membership.school_id}-${membership.role}`}
                                        className="cursor-pointer gap-3 py-2.5"
                                        onSelect={() => void switchSchool(membership.school_id)}
                                    >
                                        {membership.school.logo_url ? (
                                            // eslint-disable-next-line @next/next/no-img-element
                                            <img
                                                src={membership.school.logo_url}
                                                alt=""
                                                className="h-8 w-8 shrink-0 rounded-md border object-cover"
                                            />
                                        ) : (
                                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border bg-muted font-semibold">
                                                {membership.school.name.slice(0, 1).toUpperCase()}
                                            </div>
                                        )}
                                        <div className="min-w-0 flex-1">
                                            <div className="truncate font-medium">{membership.school.name}</div>
                                            <div className="flex items-center gap-2 text-xs capitalize text-muted-foreground">
                                                <span>{membership.role.replaceAll("_", " ")}</span>
                                                {membership.school.is_registered && <span>• Verified</span>}
                                            </div>
                                        </div>
                                        {active && <Check className="h-4 w-4 shrink-0" />}
                                    </DropdownMenuItem>
                                )
                            })}
                        </DropdownMenuContent>
                    </DropdownMenu>
                ) : (
                    workspace && schoolIdentity
                )}

                <DropdownMenu
                    onOpenChange={(open) => {
                        if (open) markAllAsRead()
                    }}
                >
                    <DropdownMenuTrigger asChild>
                        <Button
                            variant="ghost"
                            size="icon"
                            className="relative"
                        >
                            <Bell className="h-5 w-5" />

                            {unreadCount > 0 && (
                                <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-xs font-bold text-white">
                                    {unreadCount > 99 ? "99+" : unreadCount}
                                </span>
                            )}
                        </Button>
                    </DropdownMenuTrigger>

                    <DropdownMenuContent align="end" className="w-80">
                        <DropdownMenuLabel className="flex items-center justify-between">
                            <span>Notifications</span>

                            {notifications.length > 0 && (
                                <button
                                    type="button"
                                    onClick={clearNotifications}
                                    className="text-xs text-muted-foreground hover:text-foreground"
                                >
                                    Clear
                                </button>
                            )}
                        </DropdownMenuLabel>

                        <DropdownMenuSeparator />

                        {notifications.length === 0 ? (
                            <DropdownMenuItem className="text-muted-foreground">
                                No notifications yet
                            </DropdownMenuItem>
                        ) : (
                            <div className="max-h-96 overflow-y-auto">
                                {notifications.map((item) => (
                                    <DropdownMenuItem
                                        key={item.id}
                                        className="flex cursor-pointer flex-col items-start gap-1 whitespace-normal"
                                    >
                                        <div className="flex w-full items-center justify-between gap-2">
                                            <span className="font-medium">
                                                {item.title}
                                            </span>

                                            {!item.isRead && (
                                                <span className="h-2 w-2 rounded-full bg-red-500" />
                                            )}
                                        </div>

                                        <span className="text-xs text-muted-foreground">
                                            {item.message}
                                        </span>

                                        <span className="text-[11px] text-muted-foreground">
                                            {new Date(item.createdAt).toLocaleString()}
                                        </span>
                                    </DropdownMenuItem>
                                ))}
                            </div>
                        )}
                    </DropdownMenuContent>
                </DropdownMenu>

                <ThemeToggle />
                <UserDropdown />
            </div>
        </header>
    )
}
