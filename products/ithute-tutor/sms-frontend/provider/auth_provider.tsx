"use client";

import { JSX, ReactNode, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { getDashboardRoute } from "@/lib/dashbaoardRoutes";
import { getCurrentUserThunk } from "@/store/features/thunks/authThunks";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

const publicRoutes = new Set(["/", "/login", "/register", "/forgot-password"]);

interface AuthProviderProps {
    children: ReactNode;
}

function SessionLoader({ label = "Opening Ithute Tutor" }: { label?: string }) {
    return (
        <div className="grid min-h-screen place-items-center bg-background px-6">
            <div className="text-center">
                <div className="mx-auto h-9 w-9 animate-spin rounded-full border-2 border-primary/20 border-t-primary" />
                <p className="mt-4 text-sm font-semibold text-foreground">{label}</p>
                <p className="mt-1 text-xs text-muted-foreground">Checking your secure session…</p>
            </div>
        </div>
    );
}

const AuthProvider = ({ children }: AuthProviderProps): JSX.Element => {
    const dispatch = useAppDispatch();
    const router = useRouter();
    const pathname = usePathname();
    const { user, status, error } = useAppSelector((state) => state.auth);
    const isPublicRoute = publicRoutes.has(pathname);

    // Bootstrap exactly once. Route changes must not repeatedly probe /auth/me.
    useEffect(() => {
        if (status === "idle") {
            void dispatch(getCurrentUserThunk());
        }
    }, [dispatch, status]);

    // AuthProvider is the only component that owns login/dashboard navigation.
    useEffect(() => {
        if (status === "authenticated" && user && isPublicRoute) {
            router.replace(getDashboardRoute(user.role));
            return;
        }

        if (status === "anonymous" && !isPublicRoute) {
            const safeNext = pathname.startsWith("/") ? pathname : "/dashboard";
            router.replace(`/login?next=${encodeURIComponent(safeNext)}`);
        }
    }, [isPublicRoute, pathname, router, status, user]);

    if (status === "idle" || status === "checking") {
        return <SessionLoader />;
    }

    if (status === "unavailable" && !user) {
        return (
            <div className="grid min-h-screen place-items-center bg-background px-6">
                <div className="w-full max-w-md rounded-2xl border bg-card p-6 text-center shadow-sm">
                    <h1 className="text-lg font-bold">Tutor session service is temporarily unavailable</h1>
                    <p className="mt-2 text-sm text-muted-foreground">
                        {error || "Ithute Tutor could not verify your session right now. Your session has not been cleared."}
                    </p>
                    <button
                        type="button"
                        onClick={() => void dispatch(getCurrentUserThunk())}
                        className="mt-5 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground"
                    >
                        Try again
                    </button>
                </div>
            </div>
        );
    }

    if (status === "authenticated" && user && isPublicRoute) {
        return <SessionLoader label="Taking you to your workspace" />;
    }

    if (status === "anonymous" && !isPublicRoute) {
        return <SessionLoader label="Returning to sign in" />;
    }

    return <>{children}</>;
};

export default AuthProvider;
