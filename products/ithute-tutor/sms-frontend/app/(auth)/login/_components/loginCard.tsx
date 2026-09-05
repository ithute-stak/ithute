"use client";

import React, { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Building2, Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import {
    beginCentralLogin,
    linkCentralAccount,
    provisionTutorProfile,
} from "@/api/auth/actions";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/customUI/password-input";


type Mode = "choose" | "link" | "new";

export const LoginCard = () => {
    const router = useRouter();
    const searchParams = useSearchParams();
    const linkRequired = searchParams.get("link_required") === "1";
    const [mode, setMode] = useState<Mode>(linkRequired ? "choose" : "choose");
    const [loading, setLoading] = useState(false);
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [username, setUsername] = useState("");

    const handleCentralLogin = () => {
        setLoading(true);
        beginCentralLogin();
    };

    const handleLink = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setLoading(true);
        try {
            await linkCentralAccount(email, password);
            toast.success("Tutor profile linked to your !thute account");
            router.replace("/dashboard");
            router.refresh();
        } catch (error) {
            const message = error instanceof Error ? error.message : "Unable to link Tutor profile";
            toast.error(message);
        } finally {
            setLoading(false);
        }
    };

    const handleNewProfile = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setLoading(true);
        try {
            await provisionTutorProfile(username, email);
            toast.success("Your !thute Tutor profile is ready");
            router.replace("/onboarding/school");
            router.refresh();
        } catch (error) {
            const message = error instanceof Error ? error.message : "Unable to create Tutor profile";
            toast.error(message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <Card className="w-full max-w-md border-0 shadow-2xl rounded-2xl bg-white/80 backdrop-blur-xl">
            <CardHeader className="space-y-2 text-center">
                <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-slate-950 text-white">
                    <ShieldCheck className="size-6" />
                </div>
                <CardTitle className="text-2xl font-semibold">
                    {linkRequired ? "Complete your Tutor setup" : "Welcome to !thute Tutor"}
                </CardTitle>
                <CardDescription>
                    {linkRequired
                        ? "Your central !thute account is signed in. Link an existing Tutor profile or create a new Tutor profile."
                        : "Tutor uses your central !thute account. One identity works across Ithute products."}
                </CardDescription>
            </CardHeader>

            <CardContent className="flex flex-col gap-5">
                {!linkRequired ? (
                    <Button
                        className="h-11 w-full text-base font-medium"
                        type="button"
                        disabled={loading}
                        onClick={handleCentralLogin}
                    >
                        {loading && <Loader2 className="mr-2 size-5 animate-spin" />}
                        Continue with !thute
                    </Button>
                ) : mode === "choose" ? (
                    <div className="grid gap-3">
                        <Button
                            className="h-auto justify-start gap-3 p-4 text-left"
                            type="button"
                            variant="outline"
                            onClick={() => setMode("new")}
                        >
                            <Building2 className="size-5 shrink-0" />
                            <span>
                                <span className="block font-semibold">I&apos;m new to Tutor</span>
                                <span className="block text-xs font-normal text-muted-foreground">
                                    Create your Tutor profile and open a school workspace.
                                </span>
                            </span>
                        </Button>
                        <Button
                            className="h-auto justify-start gap-3 p-4 text-left"
                            type="button"
                            variant="outline"
                            onClick={() => setMode("link")}
                        >
                            <ShieldCheck className="size-5 shrink-0" />
                            <span>
                                <span className="block font-semibold">I already used Tutor</span>
                                <span className="block text-xs font-normal text-muted-foreground">
                                    Prove your old Tutor credentials once and link the profile safely.
                                </span>
                            </span>
                        </Button>
                        <Button type="button" variant="ghost" onClick={handleCentralLogin} disabled={loading}>
                            Use a different !thute account
                        </Button>
                    </div>
                ) : mode === "link" ? (
                    <form onSubmit={handleLink} className="grid gap-4">
                        <div className="grid gap-2">
                            <Label htmlFor="legacy-email">Existing Tutor email</Label>
                            <Input
                                id="legacy-email"
                                type="email"
                                value={email}
                                onChange={(event) => setEmail(event.target.value)}
                                required
                                disabled={loading}
                            />
                        </div>
                        <div className="grid gap-2">
                            <Label htmlFor="legacy-password">Existing Tutor password</Label>
                            <PasswordInput
                                id="legacy-password"
                                value={password}
                                onChange={(event) => setPassword(event.target.value)}
                                required
                                disabled={loading}
                            />
                        </div>
                        <Button className="h-11 w-full" type="submit" disabled={loading}>
                            {loading && <Loader2 className="mr-2 size-5 animate-spin" />}
                            Link existing profile
                        </Button>
                        <Button type="button" variant="ghost" onClick={() => setMode("choose")} disabled={loading}>
                            Back
                        </Button>
                    </form>
                ) : (
                    <form onSubmit={handleNewProfile} className="grid gap-4">
                        <div className="grid gap-2">
                            <Label htmlFor="new-name">Your name</Label>
                            <Input
                                id="new-name"
                                value={username}
                                onChange={(event) => setUsername(event.target.value)}
                                required
                                minLength={2}
                                disabled={loading}
                            />
                        </div>
                        <div className="grid gap-2">
                            <Label htmlFor="new-email">Email</Label>
                            <Input
                                id="new-email"
                                type="email"
                                value={email}
                                onChange={(event) => setEmail(event.target.value)}
                                required
                                disabled={loading}
                            />
                        </div>
                        <p className="text-xs text-muted-foreground">
                            If your central !thute account has a verified email, this email must match it. We do not merge profiles just because emails look alike.
                        </p>
                        <Button className="h-11 w-full" type="submit" disabled={loading}>
                            {loading && <Loader2 className="mr-2 size-5 animate-spin" />}
                            Create Tutor profile
                        </Button>
                        <Button type="button" variant="ghost" onClick={() => setMode("choose")} disabled={loading}>
                            Back
                        </Button>
                    </form>
                )}
            </CardContent>
        </Card>
    );
};
