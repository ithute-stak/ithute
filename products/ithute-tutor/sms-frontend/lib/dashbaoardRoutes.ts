import {UserRole} from "@/types/shared.primitive";


export const getDashboardRoute = (role: UserRole): string => {
    switch (role) {
        case UserRole.super_admin:
            return "/dashboard";

        case UserRole.school_admin:
            return "/school-admin/dashboard";

        case UserRole.teacher:
            return "/teacher/dashboard";

        case UserRole.student:
            return "/student/dashboard";

        case UserRole.parent:
            return "/parent/dashboard";

        default:
            return "/login";
    }
};