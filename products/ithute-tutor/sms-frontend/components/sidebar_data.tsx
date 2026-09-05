import { ReactNode } from "react";
import {
    LayoutDashboardIcon,
    UsersIcon,
    GraduationCapIcon,
    BookOpenIcon,
    ClipboardListIcon,
    CreditCardIcon,
    SettingsIcon,
    SchoolIcon,
    UserIcon,
    CalendarIcon,
    ClipboardCheckIcon,
    FileTextIcon,
    ReceiptIcon,
    BuildingIcon,
    PaletteIcon,
    BrainIcon,
    WrenchIcon,
    BriefcaseBusinessIcon,
    UserPlusIcon,
    HeartPulseIcon,
} from "lucide-react";
import {UserAuthResponse} from "@/types/user";

export interface SidebarUser { name: string; email: string; avatar: string }
export interface NavItem { title: string; url: string; icon: ReactNode }
export interface NavGroup { title: string; icon: ReactNode; url?: string; items?: NavItem[] }
export interface SidebarData { user: SidebarUser; navMain: NavGroup[]; navSecondary: NavItem[] }

export const sidebarData = (user: UserAuthResponse | null): SidebarData => ({
    user: { name: user?.name ?? "", email: user?.email ?? "", avatar: "/logo.png" },
    navMain: [
        { title: "Dashboard", url: "/dashboard", icon: <LayoutDashboardIcon /> },
        { title: "!thute Tutor", url: "/dashboard/tutor", icon: <BrainIcon /> },
        {
            title: "Student Management",
            icon: <UsersIcon />,
            items: [
                { title: "All Students", url: "/dashboard/students", icon: <UserIcon /> },
                { title: "Applications", url: "/dashboard/admissions", icon: <UserPlusIcon /> },
                { title: "Admissions & Transfers", url: "/dashboard/students/admissions", icon: <ClipboardCheckIcon /> },
                { title: "Attendance", url: "/dashboard/students/attendance", icon: <CalendarIcon /> },
                { title: "Student Care & Records", url: "/dashboard/student-care", icon: <HeartPulseIcon /> },
            ],
        },
        {
            title: "Employee Management",
            icon: <GraduationCapIcon />,
            items: [
                { title: "All Teachers", url: "/dashboard/teachers", icon: <UserIcon /> },
                { title: "Teaching Load", url: "/dashboard/teachers/schedules", icon: <CalendarIcon /> },
                { title: "Administration", url: "/dashboard/administration", icon: <BriefcaseBusinessIcon /> },
            ],
        },
        {
            title: "Academics",
            icon: <BookOpenIcon />,
            items: [
                { title: "Academic Center", url: "/dashboard/academics", icon: <GraduationCapIcon /> },
                { title: "Learning Center", url: "/dashboard/learning", icon: <BookOpenIcon /> },
                { title: "Shared Learning Library", url: "/dashboard/learning-library", icon: <BookOpenIcon /> },
                { title: "Classes & Courses", url: "/dashboard/course", icon: <BookOpenIcon /> },
                { title: "Subjects", url: "/dashboard/subjects", icon: <FileTextIcon /> },
                { title: "Timetable", url: "/dashboard/timetable", icon: <CalendarIcon /> },
            ],
        },
        {
            title: "Assessments & Results",
            icon: <ClipboardListIcon />,
            items: [
                { title: "Assessments", url: "/dashboard/exams", icon: <ClipboardListIcon /> },
                { title: "Online Quizzes", url: "/dashboard/quiz", icon: <ClipboardCheckIcon /> },
                { title: "Results & Report Cards", url: "/dashboard/results", icon: <FileTextIcon /> },
            ],
        },
        {
            title: "Finance",
            icon: <CreditCardIcon />,
            items: [
                { title: "Fees & Billing", url: "/dashboard/fees", icon: <ReceiptIcon /> },
                { title: "Employee Payments", url: "/dashboard/payments?employee", icon: <CreditCardIcon /> },
                { title: "Procurement & Expenses", url: "/dashboard/administration", icon: <BriefcaseBusinessIcon /> },
            ],
        },
        {
            title: "School",
            icon: <SchoolIcon />,
            items: [
                { title: "School Profile", url: "/dashboard/school-profile", icon: <PaletteIcon /> },
                { title: "Departments", url: "/dashboard/departments", icon: <BuildingIcon /> },
                { title: "Events", url: "/dashboard/events", icon: <CalendarIcon /> },
                { title: "Operations", url: "/dashboard/operations", icon: <WrenchIcon /> },
                { title: "Reports", url: "/dashboard/reports", icon: <FileTextIcon /> },
            ],
        },
    ],
    navSecondary: [{ title: "Settings", url: "/dashboard/settings", icon: <SettingsIcon /> }],
});
