"use client"

import { FormEvent, useEffect, useMemo, useState } from "react"
import { Building2, CheckCircle2, ShieldCheck } from "lucide-react"
import { toast } from "sonner"

import { updateSchoolProfile } from "@/api/schools/workspace"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"


type FormState = {
  name: string
  motto: string
  logo_url: string
  address: string
  phone: string
  email: string
  website: string
  primary_color: string
  secondary_color: string
  accent_color: string
  timezone: string
  currency: string
  locale: string
}

const EMPTY_FORM: FormState = {
  name: "",
  motto: "",
  logo_url: "",
  address: "",
  phone: "",
  email: "",
  website: "",
  primary_color: "",
  secondary_color: "",
  accent_color: "",
  timezone: "Africa/Maseru",
  currency: "LSL",
  locale: "en-LS",
}

export default function SchoolProfilePage() {
  const { workspace, loading, refreshWorkspace } = useSchoolWorkspace()
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  const canManage = useMemo(
    () => workspace?.capabilities.includes("*") || workspace?.capabilities.includes("school.manage"),
    [workspace],
  )

  useEffect(() => {
    const school = workspace?.school
    if (!school) return
    setForm({
      name: school.name ?? "",
      motto: school.motto ?? "",
      logo_url: school.logo_url ?? "",
      address: school.address ?? "",
      phone: school.phone ?? "",
      email: school.email ?? "",
      website: school.website ?? "",
      primary_color: school.primary_color ?? "",
      secondary_color: school.secondary_color ?? "",
      accent_color: school.accent_color ?? "",
      timezone: school.timezone ?? "Africa/Maseru",
      currency: school.currency ?? "LSL",
      locale: school.locale ?? "en-LS",
    })
  }, [workspace])

  const setField = (field: keyof FormState, value: string) => {
    setForm((current) => ({ ...current, [field]: value }))
  }

  const saveProfile = async (event: FormEvent) => {
    event.preventDefault()
    if (!workspace || !canManage) return

    setSaving(true)
    try {
      await updateSchoolProfile(workspace.school.id, {
        name: form.name.trim(),
        motto: form.motto.trim() || null,
        logo_url: form.logo_url.trim() || null,
        address: form.address.trim() || null,
        phone: form.phone.trim() || null,
        email: form.email.trim() || null,
        website: form.website.trim() || null,
        primary_color: form.primary_color.trim() || null,
        secondary_color: form.secondary_color.trim() || null,
        accent_color: form.accent_color.trim() || null,
        timezone: form.timezone.trim() || "Africa/Maseru",
        currency: form.currency.trim().toUpperCase() || "LSL",
        locale: form.locale.trim() || "en-LS",
      })
      await refreshWorkspace()
      toast.success("School profile updated")
    } catch {
      toast.error("Could not update the school profile")
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading school workspace…</div>
  }

  if (!workspace) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Select a school workspace</CardTitle>
          <CardDescription>Choose a school from the header before editing its profile.</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  const school = workspace.school

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 rounded-3xl border bg-muted/20 p-6 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-4">
          <div
            className="flex size-14 items-center justify-center rounded-2xl border text-xl font-bold"
            style={school.primary_color ? { backgroundColor: school.primary_color, color: "white" } : undefined}
          >
            {school.name.slice(0, 1).toUpperCase()}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold">{school.name}</h1>
              {school.is_registered && <CheckCircle2 className="h-5 w-5 text-emerald-600" />}
            </div>
            <p className="text-sm text-muted-foreground">
              This profile controls how your school workspace appears across !thute Tutor.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-full border bg-background px-3 py-1.5 text-xs text-muted-foreground">
          <ShieldCheck className="h-4 w-4" />
          {school.is_registered ? "Verified school" : "Profile active · verification pending"}
        </div>
      </div>

      <form onSubmit={saveProfile} className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Building2 className="h-5 w-5" /> School identity</CardTitle>
            <CardDescription>Branding and contact information visible inside this school workspace.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5 md:grid-cols-2">
            <div className="grid gap-2 md:col-span-2">
              <Label htmlFor="school-name">School name</Label>
              <Input id="school-name" value={form.name} onChange={(e) => setField("name", e.target.value)} disabled={!canManage} required />
            </div>
            <div className="grid gap-2 md:col-span-2">
              <Label htmlFor="motto">Motto</Label>
              <Input id="motto" value={form.motto} onChange={(e) => setField("motto", e.target.value)} disabled={!canManage} />
            </div>
            <div className="grid gap-2 md:col-span-2">
              <Label htmlFor="logo-url">Logo URL</Label>
              <Input id="logo-url" value={form.logo_url} onChange={(e) => setField("logo_url", e.target.value)} disabled={!canManage} placeholder="https://… or /media/…" />
            </div>
            <div className="grid gap-2 md:col-span-2">
              <Label htmlFor="address">Address</Label>
              <textarea id="address" value={form.address} onChange={(e) => setField("address", e.target.value)} disabled={!canManage} className="min-h-24 rounded-md border bg-background px-3 py-2 text-sm" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="phone">Phone</Label>
              <Input id="phone" value={form.phone} onChange={(e) => setField("phone", e.target.value)} disabled={!canManage} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="email">School email</Label>
              <Input id="email" type="email" value={form.email} onChange={(e) => setField("email", e.target.value)} disabled={!canManage} />
            </div>
            <div className="grid gap-2 md:col-span-2">
              <Label htmlFor="website">Website</Label>
              <Input id="website" value={form.website} onChange={(e) => setField("website", e.target.value)} disabled={!canManage} />
            </div>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Workspace branding</CardTitle>
              <CardDescription>School-specific visual identity.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {(["primary_color", "secondary_color", "accent_color"] as const).map((field) => (
                <div className="grid gap-2" key={field}>
                  <Label htmlFor={field}>{field.replace("_", " ")}</Label>
                  <div className="flex gap-2">
                    <Input id={field} value={form[field]} onChange={(e) => setField(field, e.target.value)} disabled={!canManage} placeholder="#1d4ed8" />
                    <input type="color" value={form[field] || "#1d4ed8"} onChange={(e) => setField(field, e.target.value)} disabled={!canManage} className="h-9 w-12 rounded border bg-background p-1" />
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Regional settings</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-2">
                <Label htmlFor="timezone">Timezone</Label>
                <Input id="timezone" value={form.timezone} onChange={(e) => setField("timezone", e.target.value)} disabled={!canManage} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="currency">Currency</Label>
                <Input id="currency" value={form.currency} onChange={(e) => setField("currency", e.target.value)} disabled={!canManage} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="locale">Locale</Label>
                <Input id="locale" value={form.locale} onChange={(e) => setField("locale", e.target.value)} disabled={!canManage} />
              </div>
            </CardContent>
          </Card>

          {canManage ? (
            <Button className="w-full" type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save school profile"}
            </Button>
          ) : (
            <p className="rounded-lg border bg-muted/30 p-3 text-sm text-muted-foreground">
              Your role can view this school profile but cannot change it.
            </p>
          )}
        </div>
      </form>
    </div>
  )
}
