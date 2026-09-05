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

const AuthProvider = ({ children }: AuthProviderProps): JSX.Element => {
    const dispatch = useAppDispatch();
    const router = useRouter();
    const pathname = usePathname();
    const { user } = useAppSelector((state) => state.auth);
    const isPublicRoute = publicRoutes.has(pathname);

    useEffect(() => {
        let active = true;

        if (user) {
            if (isPublicRoute && pathname !== "/") {
                router.replace(getDashboardRoute(user.role));
            }
            return () => {
                active = false;
            };
        }

        dispatch(getCurrentUserThunk())
            .unwrap()
            .then((resolvedUser) => {
                if (!active) return;
                if (isPublicRoute && pathname !== "/") {
                    router.replace(getDashboardRoute(resolvedUser.role));
                }
            })
            .catch(() => {
                if (!active) return;
                if (!isPublicRoute) {
                    router.replace("/login");
                }
            });

        return () => {
            active = false;
        };
    }, [dispatch, isPublicRoute, pathname, router, user]);

    return <>{children}</>;
};

export default AuthProvider;
