"use client"

import { FormEvent, useState } from "react"
import { useRouter } from "next/navigation"
import { Building2, Loader2, ShieldCheck } from "lucide-react"
import { toast } from "sonner"

import {
  activateSchoolWorkspace,
  createSchoolWorkspace,
} from "@/api/schools/workspace"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"


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

export default function SchoolOnboardingPage() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({
    name: "",
    category: "primary_school",
    school_code: "",
    registration_number: "",
    motto: "",
    address: "",
    phone: "",
    email: "",
    website: "",
  })

  const setField = (field: keyof typeof form, value: string) => {
    setForm((current) => ({ ...current, [field]: value }))
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    try {
      const school = await createSchoolWorkspace({
        name: form.name.trim(),
        category: form.category,
        school_code: form.school_code.trim() || null,
        registration_number: form.registration_number.trim() || null,
        motto: form.motto.trim() || null,
        address: form.address.trim() || null,
        phone: form.phone.trim() || null,
        email: form.email.trim() || null,
        website: form.website.trim() || null,
      })
      await activateSchoolWorkspace(school.id)
      toast.success(`${school.name} workspace created`)
      router.replace("/dashboard/school-profile")
      router.refresh()
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to create school workspace"
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen bg-muted/20 px-4 py-10 md:py-16">
      <div className="mx-auto grid max-w-5xl gap-6 lg:grid-cols-[1fr_1.35fr]">
        <div className="flex flex-col justify-center rounded-3xl bg-slate-950 p-8 text-white lg:p-10">
          <div className="mb-6 flex size-14 items-center justify-center rounded-2xl bg-white/10">
            <Building2 className="size-7" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight">Open your school on !thute Tutor</h1>
          <p className="mt-4 text-sm leading-6 text-slate-300">
            Your school gets its own private workspace, branding, students, teachers, finance, academics,
            reports and settings while remaining connected to the wider !thute education ecosystem.
          </p>
          <div className="mt-8 space-y-3 text-sm text-slate-200">
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 size-4 shrink-0" />
              <span>Other schools cannot see your operational data.</span>
            </div>
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 size-4 shrink-0" />
              <span>Learners keep one education identity even when they later transfer schools.</span>
            </div>
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 size-4 shrink-0" />
              <span>School registration verification is separate from opening and configuring your workspace.</span>
            </div>
          </div>
        </div>

        <Card className="rounded-3xl">
          <CardHeader>
            <CardTitle>School profile</CardTitle>
            <CardDescription>
              Start with the basics. You can finish branding, fees, classes, staff and academic settings after creation.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="grid gap-5 md:grid-cols-2">
              <div className="grid gap-2 md:col-span-2">
                <Label htmlFor="name">School name</Label>
                <Input
                  id="name"
                  value={form.name}
                  onChange={(event) => setField("name", event.target.value)}
                  placeholder="Example Academy"
                  minLength={2}
                  required
                  disabled={loading}
                />
              </div>

              <div className="grid gap-2">
                <Label htmlFor="category">School category</Label>
                <select
                  id="category"
                  value={form.category}
                  onChange={(event) => setField("category", event.target.value)}
                  disabled={loading}
                  className="h-9 rounded-md border bg-background px-3 text-sm"
                >
                  {SCHOOL_CATEGORIES.map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>

              <div className="grid gap-2">
                <Label htmlFor="school-code">School code</Label>
                <Input
                  id="school-code"
                  value={form.school_code}
                  onChange={(event) => setField("school_code", event.target.value)}
                  placeholder="Optional"
                  disabled={loading}
                />
              </div>

              <div className="grid gap-2 md:col-span-2">
                <Label htmlFor="registration-number">Registration number</Label>
                <Input
                  id="registration-number"
                  value={form.registration_number}
                  onChange={(event) => setField("registration_number", event.target.value)}
                  placeholder="Optional — does not automatically verify the school"
                  disabled={loading}
                />
              </div>

              <div className="grid gap-2 md:col-span-2">
                <Label htmlFor="motto">Motto</Label>
                <Input
                  id="motto"
                  value={form.motto}
                  onChange={(event) => setField("motto", event.target.value)}
                  placeholder="Optional"
                  disabled={loading}
                />
              </div>

              <div className="grid gap-2 md:col-span-2">
                <Label htmlFor="address">Address</Label>
                <textarea
                  id="address"
                  value={form.address}
                  onChange={(event) => setField("address", event.target.value)}
                  className="min-h-20 rounded-md border bg-background px-3 py-2 text-sm"
                  disabled={loading}
                />
              </div>

              <div className="grid gap-2">
                <Label htmlFor="phone">School phone</Label>
                <Input
                  id="phone"
                  value={form.phone}
                  onChange={(event) => setField("phone", event.target.value)}
                  disabled={loading}
                />
              </div>

              <div className="grid gap-2">
                <Label htmlFor="email">School email</Label>
                <Input
                  id="email"
                  type="email"
                  value={form.email}
                  onChange={(event) => setField("email", event.target.value)}
                  disabled={loading}
                />
              </div>

              <div className="grid gap-2 md:col-span-2">
                <Label htmlFor="website">Website</Label>
                <Input
                  id="website"
                  value={form.website}
                  onChange={(event) => setField("website", event.target.value)}
                  placeholder="https://…"
                  disabled={loading}
                />
              </div>

              <Button type="submit" className="h-11 md:col-span-2" disabled={loading}>
                {loading && <Loader2 className="mr-2 size-4 animate-spin" />}
                Create school workspace
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </main>
  )
}
