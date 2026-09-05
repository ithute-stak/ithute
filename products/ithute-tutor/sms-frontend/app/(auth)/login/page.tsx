"use client"
import {LoginCard} from "./_components/loginCard";
import {LoginLeftSide} from "./_components/login_left";

export default function LoginPage() {
    return (
        <div className="min-h-screen grid grid-cols-1 md:grid-cols-2 bg-linear-to-br from-slate-50 via-white to-slate-100">

            {/* ================= LEFT SIDE ================= */}
            <LoginLeftSide/>
            {/* ================= RIGHT SIDE ================= */}
            <div className="flex items-center justify-center p-6">
                <LoginCard/>
            </div>
        </div>
    )
}