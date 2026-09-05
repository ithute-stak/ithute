"use client"

import * as React from "react"
import { NavMain } from "@/components/nav-main"
import { NavSecondary } from "@/components/nav-secondary"
import { NavUser } from "@/components/nav-user"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import Link from "next/link";
import {useAppSelector} from "@/store/hooks";
import {sidebarData} from "@/components/sidebar_data";
import {useSchoolWorkspace} from "@/provider/school_workspace_provider";

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { user } = useAppSelector((state) => state.auth);
  const { workspace } = useSchoolWorkspace();
  const data = sidebarData(user)
  const schoolName = workspace?.school.name ?? "!thute Tutor"
  const schoolInitial = schoolName.slice(0, 1).toUpperCase()

  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              className="data-[slot=sidebar-menu-button]:h-auto data-[slot=sidebar-menu-button]:p-2!"
            >
              <Link href="/dashboard" className="items-center gap-3">
                <div
                  className="flex size-9 shrink-0 items-center justify-center rounded-lg border text-sm font-bold"
                  style={workspace?.school.primary_color ? {
                    backgroundColor: workspace.school.primary_color,
                    color: "white",
                  } : undefined}
                >
                  {schoolInitial}
                </div>
                <div className="min-w-0 flex-1 leading-tight">
                  <div className="truncate text-sm font-semibold">{schoolName}</div>
                  <div className="truncate text-[10px] text-muted-foreground">
                    Powered by !thute Tutor
                  </div>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={data.navMain} />
        <NavSecondary items={data.navSecondary} className="mt-auto" />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={data.user} />
      </SidebarFooter>
    </Sidebar>
  )
}
