"use client";

import { useRouter } from "next/navigation";

import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuGroup,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

import {
    BookOpenIcon,
    ChevronDownIcon,
    Layers2Icon,
    LogOutIcon,
    PinIcon,
    UserPenIcon,
} from "lucide-react";

import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { logoutThunk } from "@/store/features/thunks/authThunks";

export const UserDropdown = () => {
    const router = useRouter();
    const dispatch = useAppDispatch();
    const { user } = useAppSelector((state) => state.auth);

    const handleLogout = () => {
        dispatch(logoutThunk());
    };

    return (
        <DropdownMenu>
            {/* Trigger */}
            <DropdownMenuTrigger asChild>
                <div className="flex items-center gap-2 px-2 cursor-pointer hover:bg-accent rounded-md">
                    <Avatar className="h-8 w-8">
                        <AvatarImage src="/logo.png" alt="User" />
                        <AvatarFallback>
                            {user?.name?.[0] ?? "U"}
                        </AvatarFallback>
                    </Avatar>

                    <ChevronDownIcon className="h-4 w-4 text-muted-foreground" />
                </div>
            </DropdownMenuTrigger>

            {/* Content */}
            <DropdownMenuContent
                align="end"
                className="w-60 border border-border bg-popover text-popover-foreground shadow-lg rounded-xl p-1"
            >
                {/* User Info */}
                <DropdownMenuLabel>
                    <div className="flex flex-col space-y-1 px-2 py-1">
                        <p className="text-sm font-medium">
                            {user?.name ?? ""}
                        </p>
                        <p className="text-xs text-muted-foreground">
                            {user?.email ?? ""}
                        </p>
                    </div>
                </DropdownMenuLabel>

                <DropdownMenuSeparator />

                {/* Actions */}
                <DropdownMenuGroup>
                    <DropdownMenuItem
                        onClick={() => router.push("/profile")}
                        className="cursor-pointer rounded-md focus:bg-accent"
                    >
                        <UserPenIcon className="mr-2 h-4 w-4" />
                        Profile
                    </DropdownMenuItem>

                    <DropdownMenuItem
                        onClick={() => router.push("/courses")}
                        className="cursor-pointer rounded-md focus:bg-accent"
                    >
                        <BookOpenIcon className="mr-2 h-4 w-4" />
                        My Courses
                    </DropdownMenuItem>

                    <DropdownMenuItem
                        onClick={() => router.push("/learning")}
                        className="cursor-pointer rounded-md focus:bg-accent"
                    >
                        <Layers2Icon className="mr-2 h-4 w-4" />
                        Learning Path
                    </DropdownMenuItem>

                    <DropdownMenuItem
                        onClick={() => router.push("/saved")}
                        className="cursor-pointer rounded-md focus:bg-accent"
                    >
                        <PinIcon className="mr-2 h-4 w-4" />
                        Saved Items
                    </DropdownMenuItem>
                </DropdownMenuGroup>

                <DropdownMenuSeparator />

                {/* Logout */}
                <DropdownMenuItem
                    onClick={handleLogout}
                    className="cursor-pointer rounded-md text-red-500 focus:bg-red-500/10"
                >
                    <LogOutIcon className="mr-2 h-4 w-4" />
                    Log out
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
};