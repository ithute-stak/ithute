"use client";

import Link from "next/link";
import React, { useEffect } from "react";
import { usePathname } from "next/navigation";

import {
    SidebarGroup,
    SidebarGroupContent,
    SidebarMenu,
    SidebarMenuItem,
    SidebarMenuButton,
    SidebarMenuSub,
    SidebarMenuSubItem,
} from "@/components/ui/sidebar";

import { ChevronDownIcon } from "lucide-react";
import { NavGroup } from "@/components/sidebar_data";

export function NavMain({ items }: { items: NavGroup[] }) {
    const pathname = usePathname();
    const [open, setOpen] = React.useState<string | null>(null);

    // 🔥 Auto-open correct parent based on route
    useEffect(() => {
        items.forEach((item) => {
            if (item.items) {
                const isChildActive = item.items.some(
                    (sub) => pathname === sub.url
                );

                if (isChildActive) {
                    setOpen(item.title);
                }
            }
        });
    }, [pathname, items]);

    return (
        <SidebarGroup>
            <SidebarGroupContent className="flex flex-col gap-2">
                <SidebarMenu>
                    {items.map((item) => {
                        const isOpen = open === item.title;

                        const isParentActive =
                            item.url && pathname === item.url;

                        return (
                            <div key={item.title}>
                                {/* 🔹 Parent */}
                                <SidebarMenuItem>
                                    {item.items ? (
                                        <SidebarMenuButton
                                            onClick={() =>
                                                setOpen(isOpen ? null : item.title)
                                            }
                                            className={`flex justify-between items-center ${
                                                isOpen ? "bg-muted font-medium" : ""
                                            }`}
                                        >
                                            <div className="flex items-center gap-2">
                                                {item.icon}
                                                <span>{item.title}</span>
                                            </div>

                                            <ChevronDownIcon
                                                className={`h-4 w-4 transition-transform ${
                                                    isOpen ? "rotate-180" : ""
                                                }`}
                                            />
                                        </SidebarMenuButton>
                                    ) : (
                                        <SidebarMenuButton
                                            asChild
                                            className={
                                                isParentActive
                                                    ? "bg-muted font-medium"
                                                    : ""
                                            }
                                        >
                                            <Link href={item.url!}>
                                                {item.icon}
                                                <span>{item.title}</span>
                                            </Link>
                                        </SidebarMenuButton>
                                    )}
                                </SidebarMenuItem>

                                {/* 🔽 Children */}
                                {item.items && isOpen && (
                                    <SidebarMenuSub>
                                        {item.items.map((sub) => {
                                            const isActive =
                                                pathname === sub.url;

                                            return (
                                                <SidebarMenuSubItem key={sub.title}>
                                                    <Link
                                                        href={sub.url}
                                                        className={`flex items-center gap-2 px-6 py-1 text-sm transition ${
                                                            isActive
                                                                ? "text-primary font-medium"
                                                                : "text-muted-foreground hover:text-foreground"
                                                        }`}
                                                    >
                                                        {sub.icon}
                                                        <span>{sub.title}</span>
                                                    </Link>
                                                </SidebarMenuSubItem>
                                            );
                                        })}
                                    </SidebarMenuSub>
                                )}
                            </div>
                        );
                    })}
                </SidebarMenu>
            </SidebarGroupContent>
        </SidebarGroup>
    );
}