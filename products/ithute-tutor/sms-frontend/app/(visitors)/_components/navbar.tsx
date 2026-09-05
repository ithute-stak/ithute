"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { useAppSelector } from "@/store/hooks";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { buttonVariants } from "@/components/ui/button";
import { UserDropdown } from "@/app/(visitors)/_components/user_drop_down";

import { Menu, X } from "lucide-react";

export function Navbar() {
    const pathname = usePathname();
    const [open, setOpen] = useState(false);

    const { token, user } = useAppSelector((state) => state.auth);

    const navBarLinks = [
        { href: "/", name: "Home" },
        { href: "/courses", name: "Courses" }, // ✅ fixed typo
        { href: "/dashboard", name: "Dashboard" },
    ];

    return (
        <header className="sticky top-0 z-50 w-full border-b bg-background/80 backdrop-blur">
            <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">

                {/* 🔹 Logo */}
                <Link href="/" className="flex items-center gap-2">
                    <Image
                        src="/logo.png"
                        alt="logo"
                        width={36}
                        height={36}
                        className="rounded-md"
                    />
                    <span className="font-semibold text-lg">
                        Ithute Solutions
                    </span>
                </Link>

                {/* 🔹 Desktop Nav */}
                <nav className="hidden md:flex items-center gap-6">

                    {/* Links */}
                    <div className="flex items-center gap-4">
                        {navBarLinks.map((item) => {
                            const isActive = pathname === item.href;

                            return (
                                <Link
                                    key={item.name}
                                    href={item.href}
                                    className={`text-sm font-medium transition-colors ${
                                        isActive
                                            ? "text-primary"
                                            : "text-muted-foreground hover:text-primary"
                                    }`}
                                >
                                    {item.name}
                                </Link>
                            );
                        })}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-3">
                        <ThemeToggle />

                        {token && user ? (
                            <UserDropdown />
                        ) : (
                            <>
                                <Link
                                    href="/login"
                                    className={buttonVariants({
                                        variant: "secondary",
                                        size: "sm",
                                    })}
                                >
                                    Login
                                </Link>

                                <Link
                                    href="/register"
                                    className={buttonVariants({
                                        size: "sm",
                                    })}
                                >
                                    Get Started
                                </Link>
                            </>
                        )}
                    </div>
                </nav>

                {/* 🔹 Mobile Menu Button */}
                <button
                    className="md:hidden"
                    onClick={() => setOpen(!open)}
                >
                    {open ? <X /> : <Menu />}
                </button>
            </div>

            {/* 🔻 Mobile Menu */}
            {open && (
                <div className="md:hidden border-t px-4 py-4 space-y-4 bg-background">

                    {/* Links */}
                    <div className="flex flex-col gap-3">
                        {navBarLinks.map((item) => {
                            const isActive = pathname === item.href;

                            return (
                                <Link
                                    key={item.name}
                                    href={item.href}
                                    onClick={() => setOpen(false)}
                                    className={`text-sm font-medium ${
                                        isActive
                                            ? "text-primary"
                                            : "text-muted-foreground"
                                    }`}
                                >
                                    {item.name}
                                </Link>
                            );
                        })}
                    </div>

                    {/* Actions */}
                    <div className="flex flex-col gap-3">
                        <ThemeToggle />

                        {token && user ? (
                            <UserDropdown />
                        ) : (
                            <>
                                <Link
                                    href="/login"
                                    className={buttonVariants({ variant: "secondary" })}
                                >
                                    Login
                                </Link>

                                <Link
                                    href="/register"
                                    className={buttonVariants()}
                                >
                                    Get Started
                                </Link>
                            </>
                        )}
                    </div>
                </div>
            )}
        </header>
    );
}