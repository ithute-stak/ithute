import AuthProvider from "@/provider/auth_provider";
import React from "react";

import {SidebarInset, SidebarProvider} from "@/components/ui/sidebar";
import {AppSidebar} from "@/components/app-sidebar";
import {SiteHeader} from "@/components/site-header";
import {SchoolWorkspaceProvider} from "@/provider/school_workspace_provider";
import {SchoolWorkspaceGate} from "@/components/school-workspace-gate";

interface DashboardLayoutProps {
    children: React.ReactNode;
}

export default function DashboardLayout({children}: Readonly<DashboardLayoutProps>) {
    return (
        <AuthProvider>
            <SchoolWorkspaceProvider>
                <SidebarProvider
                    style={
                        {
                            "--sidebar-width": "calc(var(--spacing) * 72)",
                            "--header-height": "calc(var(--spacing) * 12)",
                        } as React.CSSProperties
                    }
                >
                    <AppSidebar variant="inset"/>
                    <SidebarInset>
                        <SiteHeader/>
                        <SchoolWorkspaceGate>
                            <div className="flex flex-1 flex-col">
                                <div className="@container/main flex flex-1 flex-col gap-2">
                                    <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6 px-4 lg:px-6">
                                        {children}
                                    </div>
                                </div>
                            </div>
                        </SchoolWorkspaceGate>
                    </SidebarInset>
                </SidebarProvider>
            </SchoolWorkspaceProvider>
        </AuthProvider>
    );
}
