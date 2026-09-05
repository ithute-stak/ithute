"use client"

import * as React from "react"
import { CheckCircle2, FileCheck2, HeartPulse, Loader2, ShieldAlert } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAppData } from "@/provider/dataProvider"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"
import {
  addStudentDocument,
  createDisciplineIncident,
  getDisciplineHistory,
  getHealthRecord,
  getStudentDocuments,
  reviewStudentDocument,
  updateHealthRecord,
  type DisciplineIncident,
  type HealthRecord,
  type StudentDocument,
} from "@/api/student-care"

const DOCUMENT_ROLES = ["school_admin", "principal", "vice_principal", "registrar", "admissions_officer"]
const DISCIPLINE_ROLES = ["school_admin", "principal", "vice_principal", "teacher", "class_teacher", "counsellor", "nurse"]
const HEALTH_ROLES = ["school_admin", "principal", "vice_principal", "nurse"]

type Tab = "documents" | "discipline" | "health"

export default function StudentCarePage() {
  const { students } = useAppData()
  const { workspace } = useSchoolWorkspace()
  const role = workspace?.role ?? ""
  const platform = Boolean(workspace?.is_platform_admin)
  const canDocuments = platform || DOCUMENT_ROLES.includes(role)
  const canDiscipline = platform || DISCIPLINE_ROLES.includes(role)
  const canHealth = platform || HEALTH_ROLES.includes(role)

  const [studentId, setStudentId] = React.useState("")
  const [tab, setTab] = React.useState<Tab>("documents")
  const [documents, setDocuments] = React.useState<StudentDocument[]>([])
  const [incidents, setIncidents] = React.useState<DisciplineIncident[]>([])
  const [health, setHealth] = React.useState<HealthRecord | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [message, setMessage] = React.useState<string | null>(null)

  const [documentForm, setDocumentForm] = React.useState({ document_type: "identity", title: "", storage_url: "" })
  const [incidentForm, setIncidentForm] = React.useState({ category: "conduct", severity: "low", title: "", description: "", occurred_on: new Date().toISOString().slice(0, 10), action_taken: "" })
  const [healthForm, setHealthForm] = React.useState({ allergies: "", conditions: "", medications: "", emergency_notes: "", emergency_contact: "" })

  const studentName = (id: string) => {
    const student = students.find((item) => item.id === id)
    const person = student?.user?.person
    return [person?.first_name, person?.last_name].filter(Boolean).join(" ") || student?.user?.username || student?.admission_number || "Learner"
  }

  const loadStudent = React.useCallback(async (id: string) => {
    if (!id) return
    setLoading(true); setError(null); setMessage(null)
    try {
      const [nextDocuments, nextIncidents, nextHealth] = await Promise.all([
        canDocuments ? getStudentDocuments(id) : Promise.resolve([]),
        canDiscipline ? getDisciplineHistory(id) : Promise.resolve([]),
        canHealth ? getHealthRecord(id) : Promise.resolve(null),
      ])
      setDocuments(nextDocuments)
      setIncidents(nextIncidents)
      setHealth(nextHealth)
      setHealthForm({
        allergies: nextHealth?.allergies ?? "",
        conditions: nextHealth?.conditions ?? "",
        medications: nextHealth?.medications ?? "",
        emergency_notes: nextHealth?.emergency_notes ?? "",
        emergency_contact: nextHealth?.emergency_contact ?? "",
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load learner care record")
    } finally { setLoading(false) }
  }, [canDiscipline, canDocuments, canHealth])

  React.useEffect(() => {
    if (!canDocuments && tab === "documents") setTab(canDiscipline ? "discipline" : "health")
  }, [canDiscipline, canDocuments, tab])

  const selectStudent = (id: string) => {
    setStudentId(id)
    void loadStudent(id)
  }

  const addDocument = async () => {
    if (!studentId || !documentForm.title.trim() || !documentForm.storage_url.trim()) return
    setSaving(true); setError(null); setMessage(null)
    try {
      await addStudentDocument(studentId, documentForm)
      setDocumentForm((v) => ({ ...v, title: "", storage_url: "" }))
      setMessage("Learner document added")
      setDocuments(await getStudentDocuments(studentId))
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to add document") }
    finally { setSaving(false) }
  }

  const reviewDocument = async (id: string, status: StudentDocument["status"]) => {
    setSaving(true); setError(null); setMessage(null)
    try {
      await reviewStudentDocument(id, status)
      setMessage(`Document ${status}`)
      if (studentId) setDocuments(await getStudentDocuments(studentId))
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to review document") }
    finally { setSaving(false) }
  }

  const addIncident = async () => {
    if (!studentId || !incidentForm.title.trim() || !incidentForm.description.trim()) return
    setSaving(true); setError(null); setMessage(null)
    try {
      await createDisciplineIncident({ student_id: studentId, ...incidentForm, action_taken: incidentForm.action_taken || null })
      setIncidentForm((v) => ({ ...v, title: "", description: "", action_taken: "" }))
      setMessage("Discipline/support incident recorded")
      setIncidents(await getDisciplineHistory(studentId))
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to record incident") }
    finally { setSaving(false) }
  }

  const saveHealth = async () => {
    if (!studentId) return
    setSaving(true); setError(null); setMessage(null)
    try {
      const updated = await updateHealthRecord(studentId, healthForm)
      setHealth(updated)
      setMessage("Health and emergency record updated")
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to update health record") }
    finally { setSaving(false) }
  }

  if (!canDocuments && !canDiscipline && !canHealth) {
    return <Card><CardContent className="p-10 text-center text-sm text-muted-foreground">Your role does not manage confidential learner care records.</CardContent></Card>
  }

  return <div className="space-y-6">
    <div className="rounded-2xl border bg-card p-6">
      <p className="text-sm font-medium text-muted-foreground">School-owned confidential learner records</p>
      <h1 className="mt-2 text-3xl font-bold tracking-tight">Student Care & Records</h1>
      <p className="mt-2 max-w-3xl text-sm text-muted-foreground">Manage verified admission documents, discipline/support history and restricted health/emergency records inside the selected school workspace.</p>
    </div>

    {error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}
    {message && <div className="rounded-lg border p-3 text-sm"><CheckCircle2 className="mr-2 inline h-4 w-4" />{message}</div>}

    <Card><CardHeader><CardTitle>Select learner</CardTitle><CardDescription>Only learners with a relationship to this school may be opened by the backend.</CardDescription></CardHeader><CardContent><select className="h-10 w-full max-w-xl rounded-md border bg-transparent px-3 text-sm" value={studentId} onChange={(e) => selectStudent(e.target.value)}><option value="">Select learner</option>{students.map((student) => <option key={student.id} value={student.id}>{studentName(student.id)} — {student.admission_number}</option>)}</select></CardContent></Card>

    {loading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Loading confidential record…</div>}

    {studentId && !loading && <>
      <div className="flex flex-wrap gap-2">
        {canDocuments && <Button variant={tab === "documents" ? "default" : "outline"} onClick={() => setTab("documents")}><FileCheck2 className="mr-2 h-4 w-4" />Documents</Button>}
        {canDiscipline && <Button variant={tab === "discipline" ? "default" : "outline"} onClick={() => setTab("discipline")}><ShieldAlert className="mr-2 h-4 w-4" />Discipline & support</Button>}
        {canHealth && <Button variant={tab === "health" ? "default" : "outline"} onClick={() => setTab("health")}><HeartPulse className="mr-2 h-4 w-4" />Health & emergency</Button>}
      </div>

      {tab === "documents" && canDocuments && <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Card><CardHeader><CardTitle>Verified learner documents</CardTitle></CardHeader><CardContent className="space-y-3">{documents.length === 0 ? <div className="py-8 text-center text-sm text-muted-foreground">No documents recorded.</div> : documents.map((item) => <div key={item.id} className="rounded-xl border p-4"><div className="flex flex-wrap justify-between gap-2"><div><div className="font-semibold">{item.title}</div><div className="text-xs text-muted-foreground">{item.document_type} · {item.status}</div></div><a className="text-sm underline" href={item.storage_url} target="_blank" rel="noreferrer">Open document</a></div><div className="mt-3 flex gap-2"><Button size="sm" disabled={saving || item.status === "verified"} onClick={() => void reviewDocument(item.id, "verified")}>Verify</Button><Button size="sm" variant="outline" disabled={saving || item.status === "rejected"} onClick={() => void reviewDocument(item.id, "rejected")}>Reject</Button></div></div>)}</CardContent></Card>
        <Card><CardHeader><CardTitle>Add document</CardTitle><CardDescription>Store only an approved document URL/reference; verification remains auditable.</CardDescription></CardHeader><CardContent className="space-y-3"><div className="grid gap-1.5"><Label>Document type</Label><Input value={documentForm.document_type} onChange={(e) => setDocumentForm((v) => ({ ...v, document_type: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Title</Label><Input value={documentForm.title} onChange={(e) => setDocumentForm((v) => ({ ...v, title: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Secure storage URL</Label><Input value={documentForm.storage_url} onChange={(e) => setDocumentForm((v) => ({ ...v, storage_url: e.target.value }))} placeholder="https://…" /></div><Button disabled={saving || !documentForm.title.trim() || !documentForm.storage_url.trim()} onClick={() => void addDocument()}>Add document</Button></CardContent></Card>
      </div>}

      {tab === "discipline" && canDiscipline && <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_400px]">
        <Card><CardHeader><CardTitle>Discipline & support history</CardTitle><CardDescription>Chronological school-owned record for {studentName(studentId)}.</CardDescription></CardHeader><CardContent className="space-y-3">{incidents.length === 0 ? <div className="py-8 text-center text-sm text-muted-foreground">No incidents recorded.</div> : incidents.map((item) => <div key={item.id} className="rounded-xl border p-4"><div className="flex flex-wrap justify-between gap-2"><div className="font-semibold">{item.title}</div><div className="text-xs font-medium">{item.occurred_on} · {item.severity}</div></div><div className="mt-1 text-xs text-muted-foreground">{item.category} · {item.status}</div><p className="mt-3 whitespace-pre-wrap text-sm">{item.description}</p>{item.action_taken && <p className="mt-2 text-sm text-muted-foreground">Action: {item.action_taken}</p>}</div>)}</CardContent></Card>
        <Card><CardHeader><CardTitle>Record incident</CardTitle></CardHeader><CardContent className="space-y-3"><div className="grid grid-cols-2 gap-3"><div className="grid gap-1.5"><Label>Category</Label><Input value={incidentForm.category} onChange={(e) => setIncidentForm((v) => ({ ...v, category: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Severity</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={incidentForm.severity} onChange={(e) => setIncidentForm((v) => ({ ...v, severity: e.target.value }))}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></div></div><div className="grid gap-1.5"><Label>Date</Label><Input type="date" value={incidentForm.occurred_on} onChange={(e) => setIncidentForm((v) => ({ ...v, occurred_on: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Title</Label><Input value={incidentForm.title} onChange={(e) => setIncidentForm((v) => ({ ...v, title: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Description</Label><textarea className="min-h-24 rounded-md border bg-transparent p-3 text-sm" value={incidentForm.description} onChange={(e) => setIncidentForm((v) => ({ ...v, description: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Action taken</Label><Input value={incidentForm.action_taken} onChange={(e) => setIncidentForm((v) => ({ ...v, action_taken: e.target.value }))} /></div><Button disabled={saving || !incidentForm.title.trim() || !incidentForm.description.trim()} onClick={() => void addIncident()}>Record incident</Button></CardContent></Card>
      </div>}

      {tab === "health" && canHealth && <Card><CardHeader><CardTitle>Health & emergency record</CardTitle><CardDescription>Restricted to school management and health staff. This is not a public learner profile.</CardDescription></CardHeader><CardContent className="grid gap-4 md:grid-cols-2"><div className="grid gap-1.5"><Label>Allergies</Label><textarea className="min-h-24 rounded-md border bg-transparent p-3 text-sm" value={healthForm.allergies} onChange={(e) => setHealthForm((v) => ({ ...v, allergies: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Conditions</Label><textarea className="min-h-24 rounded-md border bg-transparent p-3 text-sm" value={healthForm.conditions} onChange={(e) => setHealthForm((v) => ({ ...v, conditions: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Medications</Label><textarea className="min-h-24 rounded-md border bg-transparent p-3 text-sm" value={healthForm.medications} onChange={(e) => setHealthForm((v) => ({ ...v, medications: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Emergency notes</Label><textarea className="min-h-24 rounded-md border bg-transparent p-3 text-sm" value={healthForm.emergency_notes} onChange={(e) => setHealthForm((v) => ({ ...v, emergency_notes: e.target.value }))} /></div><div className="grid gap-1.5 md:col-span-2"><Label>Emergency contact</Label><Input value={healthForm.emergency_contact} onChange={(e) => setHealthForm((v) => ({ ...v, emergency_contact: e.target.value }))} /></div><div className="md:col-span-2"><Button disabled={saving} onClick={() => void saveHealth()}>{health ? "Update health record" : "Create health record"}</Button></div></CardContent></Card>}
    </>}
  </div>
}
