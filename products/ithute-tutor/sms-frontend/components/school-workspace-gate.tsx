"use client"

import React, { useState } from "react"
import { AlertTriangle, Building2, Loader2, School } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  activateSchoolWorkspace,
  createSchoolWorkspace,
} from "@/api/schools/workspace"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"

const SCHOOL_CATEGORIES = [
  ["pre_school", "Pre-school"],
  ["junior_school", "Junior school"],
  ["primary_school", "Primary school"],
  ["basic_education_school", "Basic education school"],
  ["secondary_school", "Secondary school"],
  ["high_school", "High school"],
  ["junior_college", "Junior college"],
  ["learning_center", "Learning centre"],
] as const

export function SchoolWorkspaceGate({ children }: { children: React.ReactNode }) {
  const { workspace, memberships, loading, refreshWorkspace } = useSchoolWorkspace()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({
    name: "",
    category: "primary_school",
    school_code: "",
    registration_number: "",
    address: "",
    phone: "",
    email: "",
  })

  if (loading) {
    return (
      <div className="flex min-h-[65vh] items-center justify-center">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Opening your school workspace…
        </div>
      </div>
    )
  }

  if (workspace) return <>{children}</>

  if (memberships.length === 1) {
    return (
      <div className="mx-auto flex min-h-[65vh] max-w-2xl items-center justify-center px-4">
        <Card className="w-full">
          <CardHeader>
            <div className="mb-2 flex h-12 w-12 items-center justify-center rounded-xl bg-amber-500/10 text-amber-700 dark:text-amber-300">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <CardTitle>School workspace could not be opened</CardTitle>
            <CardDescription>
              Your account already belongs to {memberships[0].school.name}. Tutor will not create a duplicate school profile. Retry opening the existing workspace.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => void refreshWorkspace()}>Retry school workspace</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (memberships.length > 1) {
    return (
      <div className="mx-auto flex min-h-[65vh] max-w-2xl items-center justify-center px-4">
        <Card className="w-full">
          <CardHeader>
            <div className="mb-2 flex h-12 w-12 items-center justify-center rounded-xl bg-muted">
              <Building2 className="h-6 w-6" />
            </div>
            <CardTitle>Select a school workspace</CardTitle>
            <CardDescription>
              Your account belongs to more than one school. Choose the school you want to work in from the school switcher above. Each school opens as a private workspace.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    )
  }

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSaving(true)
    setError(null)

    try {
      const school = await createSchoolWorkspace({
        name: form.name.trim(),
        category: form.category,
        school_code: form.school_code.trim() || null,
        registration_number: form.registration_number.trim() || null,
        address: form.address.trim() || null,
        phone: form.phone.trim() || null,
        email: form.email.trim() || null,
      })
      await activateSchoolWorkspace(school.id)
      window.location.reload()
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to open the school workspace"
      setError(message)
      setSaving(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-3xl items-center justify-center px-4 py-8">
      <Card className="w-full shadow-sm">
        <CardHeader className="space-y-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <School className="h-6 w-6" />
          </div>
          <div>
            <CardTitle className="text-2xl">Open your school on !thute Tutor</CardTitle>
            <CardDescription className="mt-1 max-w-2xl">
              Create the school profile that will become your private management workspace. Your students, staff, finance, academics and reports stay isolated from other schools on the platform.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="grid gap-5">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="grid gap-2 md:col-span-2">
                <Label htmlFor="school-name">School name</Label>
                <Input id="school-name" value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} placeholder="e.g. Mountain View High School" minLength={2} required disabled={saving} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="school-category">School category</Label>
                <select id="school-category" className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50" value={form.category} onChange={(event) => setForm((current) => ({ ...current, category: event.target.value }))} disabled={saving}>
                  {SCHOOL_CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="school-code">School code</Label>
                <Input id="school-code" value={form.school_code} onChange={(event) => setForm((current) => ({ ...current, school_code: event.target.value }))} placeholder="Optional" disabled={saving} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="registration-number">Registration number</Label>
                <Input id="registration-number" value={form.registration_number} onChange={(event) => setForm((current) => ({ ...current, registration_number: event.target.value }))} placeholder="Optional" disabled={saving} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="school-phone">Phone</Label>
                <Input id="school-phone" value={form.phone} onChange={(event) => setForm((current) => ({ ...current, phone: event.target.value }))} placeholder="Optional" disabled={saving} />
              </div>
              <div className="grid gap-2 md:col-span-2">
                <Label htmlFor="school-email">School email</Label>
                <Input id="school-email" type="email" value={form.email} onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} placeholder="Optional" disabled={saving} />
              </div>
              <div className="grid gap-2 md:col-span-2">
                <Label htmlFor="school-address">Address</Label>
                <Input id="school-address" value={form.address} onChange={(event) => setForm((current) => ({ ...current, address: event.target.value }))} placeholder="Optional" disabled={saving} />
              </div>
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex flex-col gap-2 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="max-w-xl text-xs text-muted-foreground">
                New school profiles start unverified. Verification by !thute confirms the institution but does not change the school's private workspace or ownership of its operational data.
              </p>
              <Button type="submit" disabled={saving || form.name.trim().length < 2} className="shrink-0">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Open school workspace
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
