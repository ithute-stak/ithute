"use client"

import * as React from "react"
import {
  ArrowLeftRight,
  CheckCircle2,
  ClipboardCopy,
  FileClock,
  Loader2,
  School,
  ShieldCheck,
  UserCheck,
  XCircle,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAppData } from "@/provider/dataProvider"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"
import {
  acceptTransfer,
  cancelTransfer,
  claimTransfer,
  getSchoolTransfers,
  getTransferRecords,
  getTransferReview,
  rejectTransfer,
  releaseTransfer,
  type LearnerTransferDossier,
  type SchoolTransfer,
  type TransferIssueResult,
  type TransferReviewPacket,
  type TransferStatus,
} from "@/api/transfers"

const MANAGER_ROLES = ["school_admin", "principal", "vice_principal", "registrar", "admissions_officer"]
const TRANSFER_REASONS = [
  "Parent / guardian request",
  "Family relocation",
  "Academic placement",
  "Boarding / day school change",
  "Programme or subject availability",
  "Other",
]

function learnerName(student: ReturnType<typeof useAppData>["students"][number] | undefined) {
  const person = student?.user?.person
  const name = [person?.first_name, person?.last_name].filter(Boolean).join(" ")
  return name || student?.user?.username || student?.admission_number || "Learner"
}

function statusLabel(status: TransferStatus) {
  return ({
    released: "Released",
    under_review: "Admission review",
    accepted: "Accepted",
    rejected: "Rejected",
    cancelled: "Cancelled",
    expired: "Expired",
  } as Record<TransferStatus, string>)[status]
}

function statusDescription(status: TransferStatus) {
  return ({
    released: "Waiting for the receiving school to claim the secure transfer.",
    under_review: "Receiving school is reviewing the learner transfer packet.",
    accepted: "Transfer completed and the receiving-school enrolment is active.",
    rejected: "Receiving school declined the transfer; source enrolment remains active.",
    cancelled: "Releasing school cancelled the transfer before completion.",
    expired: "The claim code expired before another school claimed it.",
  } as Record<TransferStatus, string>)[status]
}

export default function AdmissionsAndTransfersPage() {
  const { students, classes } = useAppData()
  const { workspace } = useSchoolWorkspace()
  const canManage = Boolean(workspace?.is_platform_admin) || MANAGER_ROLES.includes(workspace?.role ?? "")
  const today = React.useMemo(() => new Date().toISOString().slice(0, 10), [])

  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [success, setSuccess] = React.useState<string | null>(null)
  const [transfers, setTransfers] = React.useState<SchoolTransfer[]>([])
  const [issued, setIssued] = React.useState<TransferIssueResult | null>(null)
  const [review, setReview] = React.useState<TransferReviewPacket | null>(null)
  const [dossier, setDossier] = React.useState<LearnerTransferDossier | null>(null)
  const [cancelTarget, setCancelTarget] = React.useState<SchoolTransfer | null>(null)
  const [cancelReason, setCancelReason] = React.useState("")
  const [rejectReason, setRejectReason] = React.useState("")

  const [releaseForm, setReleaseForm] = React.useState({
    student_id: "",
    transfer_reason: "Parent / guardian request",
    note: "",
    consent_confirmed: false,
    validity_days: 7,
  })
  const [claimCode, setClaimCode] = React.useState("")
  const [acceptForm, setAcceptForm] = React.useState({
    class_id: "",
    start_date: today,
    records_verified: false,
    destination_note: "",
  })

  const refresh = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setTransfers(await getSchoolTransfers())
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load learner transfers")
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => { void refresh() }, [workspace?.school.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const release = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!releaseForm.student_id) return
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const result = await releaseTransfer(releaseForm.student_id, releaseForm)
      setIssued(result)
      setSuccess(`Transfer ${result.reference_number} released. The learner remains active in this school until another school reviews and accepts it.`)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to release learner transfer")
    } finally {
      setSaving(false)
    }
  }

  const claim = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!claimCode.trim()) return
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const result = await claimTransfer(claimCode.trim())
      setClaimCode("")
      setSuccess(`Transfer ${result.reference_number} claimed for admission review. No enrolment has moved yet.`)
      await refresh()
      setReview(await getTransferReview(result.transfer_id))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to claim learner transfer")
    } finally {
      setSaving(false)
    }
  }

  const openReview = async (transfer: SchoolTransfer) => {
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const packet = await getTransferReview(transfer.id)
      setReview(packet)
      setDossier(null)
      setRejectReason("")
      setAcceptForm({ class_id: transfer.destination_class_id || "", start_date: transfer.proposed_start_date || today, records_verified: false, destination_note: transfer.destination_note || "" })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to open admission review")
    } finally {
      setSaving(false)
    }
  }

  const accept = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!review || !acceptForm.class_id) return
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      await acceptTransfer(review.transfer.id, acceptForm)
      setSuccess(`Transfer ${review.transfer.reference_number || review.transfer.id} accepted. The source enrolment is now historical and this school's enrolment is active.`)
      setReview(null)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to accept learner transfer")
    } finally {
      setSaving(false)
    }
  }

  const reject = async () => {
    if (!review || rejectReason.trim().length < 3) return
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      await rejectTransfer(review.transfer.id, rejectReason.trim())
      setSuccess(`Transfer ${review.transfer.reference_number || review.transfer.id} rejected. The learner remains active at the releasing school.`)
      setReview(null)
      setRejectReason("")
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to reject learner transfer")
    } finally {
      setSaving(false)
    }
  }

  const confirmCancel = async () => {
    if (!cancelTarget || cancelReason.trim().length < 3) return
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      await cancelTransfer(cancelTarget.id, cancelReason.trim())
      setSuccess(`Transfer ${cancelTarget.reference_number || cancelTarget.id} cancelled. The learner remains enrolled in the releasing school.`)
      setCancelTarget(null)
      setCancelReason("")
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to cancel learner transfer")
    } finally {
      setSaving(false)
    }
  }

  const openRecords = async (transfer: SchoolTransfer) => {
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      setDossier(await getTransferRecords(transfer.id))
      setReview(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to open transferred learner records")
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="flex min-h-[55vh] items-center justify-center gap-3 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" />Loading admissions and transfers…</div>
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border bg-card p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground"><ArrowLeftRight className="h-4 w-4" />Professional learner handover</div>
            <h1 className="text-3xl font-bold tracking-tight">Admissions & Transfers</h1>
            <p className="mt-2 max-w-4xl text-sm text-muted-foreground">Transfers use a controlled two-school handover. The releasing school authorizes the transfer, the receiving school claims and reviews the case, and only formal acceptance moves the active enrolment.</p>
          </div>
          <Button variant="outline" onClick={() => void refresh()}>Refresh</Button>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-4">
          {[
            ["1", "Release", "School A prepares and authorizes the learner handover."],
            ["2", "Claim", "School B uses the one-time code to identify itself as receiver."],
            ["3", "Review", "School B reviews the controlled admission packet before deciding."],
            ["4", "Decision", "Accept activates School B enrolment; reject leaves School A unchanged."],
          ].map(([step, title, description]) => <div key={step} className="rounded-xl border p-3"><div className="text-xs font-semibold text-muted-foreground">STEP {step}</div><div className="mt-1 font-semibold">{title}</div><div className="mt-1 text-xs text-muted-foreground">{description}</div></div>)}
        </div>
      </div>

      {error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}
      {success && <div className="rounded-lg border p-3 text-sm"><div className="flex items-start gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4" /><span>{success}</span></div></div>}

      {canManage && <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Release learner from this school</CardTitle>
            <CardDescription>This creates a formal transfer case and secure one-time claim code. The learner stays actively enrolled here until the receiving school accepts.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form onSubmit={release} className="space-y-4">
              <div className="grid gap-1.5"><Label>Learner</Label><select className="h-9 w-full rounded-md border bg-transparent px-3 text-sm" value={releaseForm.student_id} onChange={(e) => setReleaseForm((v) => ({ ...v, student_id: e.target.value }))} required><option value="">Select active learner</option>{students.map((student) => <option key={student.id} value={student.id}>{learnerName(student)} — {student.admission_number}</option>)}</select></div>
              <div className="grid gap-1.5"><Label>Reason for transfer</Label><select className="h-9 w-full rounded-md border bg-transparent px-3 text-sm" value={releaseForm.transfer_reason} onChange={(e) => setReleaseForm((v) => ({ ...v, transfer_reason: e.target.value }))}>{TRANSFER_REASONS.map((reason) => <option key={reason}>{reason}</option>)}</select></div>
              <div className="grid gap-1.5"><Label>Handover note</Label><Input value={releaseForm.note} onChange={(e) => setReleaseForm((v) => ({ ...v, note: e.target.value }))} placeholder="Optional note for the receiving school" /></div>
              <div className="grid gap-1.5"><Label>Claim-code validity</Label><Input type="number" min={1} max={30} value={releaseForm.validity_days} onChange={(e) => setReleaseForm((v) => ({ ...v, validity_days: Number(e.target.value) }))} /></div>
              <label className="flex items-start gap-3 rounded-lg border p-3 text-sm"><input className="mt-1" type="checkbox" checked={releaseForm.consent_confirmed} onChange={(e) => setReleaseForm((v) => ({ ...v, consent_confirmed: e.target.checked }))} /><span><span className="font-medium">Transfer authorization confirmed</span><span className="mt-1 block text-xs text-muted-foreground">The school confirms that the learner / parent / guardian authorization required by the school's process has been recorded.</span></span></label>
              <Button type="submit" disabled={saving || !releaseForm.consent_confirmed}>Release transfer</Button>
            </form>

            {issued && <div className="rounded-xl border bg-muted/20 p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Transfer reference</div>
              <div className="mt-1 text-lg font-bold">{issued.reference_number}</div>
              <div className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">One-time claim code</div>
              <div className="mt-1 break-all font-mono text-lg font-bold">{issued.code}</div>
              <div className="mt-2 text-xs text-muted-foreground">Expires {new Date(issued.expires_at).toLocaleString()}. Claiming this code does not yet move the learner.</div>
              <Button className="mt-3" size="sm" variant="outline" onClick={() => void navigator.clipboard?.writeText(issued.code)}><ClipboardCopy className="mr-2 h-4 w-4" />Copy claim code</Button>
            </div>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Claim an incoming learner</CardTitle>
            <CardDescription>Enter the code supplied by the releasing school. This opens an admission review case; it does not immediately enrol the learner.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={claim} className="space-y-4">
              <div className="grid gap-1.5"><Label>One-time transfer claim code</Label><Input value={claimCode} onChange={(e) => setClaimCode(e.target.value)} placeholder="Paste the secure code from the releasing school" required /></div>
              <div className="rounded-lg border bg-muted/20 p-3 text-xs text-muted-foreground">After claiming, this school can review a limited admission packet. Full historical records remain locked until formal acceptance.</div>
              <Button type="submit" disabled={saving || !claimCode.trim()}><UserCheck className="mr-2 h-4 w-4" />Claim for admission review</Button>
            </form>
          </CardContent>
        </Card>
      </div>}

      <Card>
        <CardHeader><CardTitle>Transfer register</CardTitle><CardDescription>Every case has a permanent reference and audit timeline. Active source-school enrolment is changed only at final acceptance.</CardDescription></CardHeader>
        <CardContent>
          {transfers.length === 0 ? <div className="py-8 text-center text-sm text-muted-foreground">No transfer cases recorded for this school.</div> : <div className="space-y-3">{transfers.map((item) => {
            const student = students.find((row) => row.id === item.student_id)
            return <div key={item.id} className="rounded-xl border p-4">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">{student ? learnerName(student) : `Learner ${item.student_id.slice(0, 8)}…`}</span>
                    <span className="rounded-full border px-2 py-0.5 text-[11px]">{item.direction}</span>
                    <span className="rounded-full border px-2 py-0.5 text-[11px]">{statusLabel(item.status)}</span>
                  </div>
                  <div className="mt-1 text-xs font-medium">{item.reference_number || item.id}</div>
                  <div className="mt-1 text-xs text-muted-foreground">{statusDescription(item.status)}</div>
                  <div className="mt-2 text-xs text-muted-foreground">{item.source_school || "Source school"}{item.destination_school ? ` → ${item.destination_school}` : " → receiving school not yet claimed"}</div>
                  {item.transfer_reason && <div className="mt-1 text-xs text-muted-foreground">Reason: {item.transfer_reason}</div>}
                  {item.rejection_reason && <div className="mt-1 text-xs">Decision note: {item.rejection_reason}</div>}
                </div>
                <div className="flex flex-wrap gap-2">
                  {item.review_available && <Button variant="outline" disabled={saving} onClick={() => void openReview(item)}><ShieldCheck className="mr-2 h-4 w-4" />Review case</Button>}
                  {item.records_available && <Button variant="outline" disabled={saving} onClick={() => void openRecords(item)}><FileClock className="mr-2 h-4 w-4" />Historical record</Button>}
                  {item.direction === "outgoing" && ["released", "under_review"].includes(item.status) && <Button variant="outline" disabled={saving} onClick={() => { setCancelTarget(item); setCancelReason("") }}><XCircle className="mr-2 h-4 w-4" />Cancel transfer</Button>}
                </div>
              </div>
              {item.events.length > 0 && <div className="mt-4 border-t pt-3"><div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Audit timeline</div><div className="mt-2 flex flex-wrap gap-2">{item.events.map((event) => <div key={event.id} className="rounded-md border px-2.5 py-1.5 text-xs"><span className="font-medium">{event.event_type.replaceAll("_", " ")}</span>{event.created_at ? <span className="ml-2 text-muted-foreground">{new Date(event.created_at).toLocaleString()}</span> : null}</div>)}</div></div>}
            </div>
          })}</div>}
        </CardContent>
      </Card>

      {cancelTarget && <Card>
        <CardHeader><CardTitle>Cancel transfer {cancelTarget.reference_number}</CardTitle><CardDescription>Cancellation does not remove the learner from the releasing school. The reason becomes part of the permanent audit trail.</CardDescription></CardHeader>
        <CardContent className="space-y-3"><div className="grid gap-1.5"><Label>Cancellation reason</Label><Input value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} placeholder="Why is this transfer being cancelled?" /></div><div className="flex gap-2"><Button variant="outline" onClick={() => setCancelTarget(null)}>Keep transfer open</Button><Button disabled={saving || cancelReason.trim().length < 3} onClick={() => void confirmCancel()}>Confirm cancellation</Button></div></CardContent>
      </Card>}

      {review && <div className="space-y-5 rounded-2xl border bg-card p-6">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div><div className="flex items-center gap-2 text-sm text-muted-foreground"><ShieldCheck className="h-4 w-4" />Admission review · {review.transfer.reference_number}</div><h2 className="mt-1 text-2xl font-bold">{review.learner.first_name} {review.learner.last_name}</h2><p className="text-sm text-muted-foreground">Admission #{review.learner.admission_number} · releasing school: {review.source_school.name || "Unknown"}</p></div>
          <Button variant="outline" onClick={() => setReview(null)}>Close review</Button>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <Card><CardHeader className="pb-2"><CardDescription>Current placement</CardDescription><CardTitle className="text-base">{review.current_enrollment.grade || "Grade not tagged"} · {review.current_enrollment.class || "Class not tagged"}</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground">{review.current_enrollment.academic_year || "Year not tagged"} · {review.current_enrollment.term || "Term not tagged"}</CardContent></Card>
          <Card><CardHeader className="pb-2"><CardDescription>Attendance reviewed</CardDescription><CardTitle className="text-base">{review.attendance_summary.records_reviewed} records</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground">Present {review.attendance_summary.present} · Absent {review.attendance_summary.absent} · Late {review.attendance_summary.late} · Excused {review.attendance_summary.excused}</CardContent></Card>
          <Card><CardHeader className="pb-2"><CardDescription>Published academic evidence</CardDescription><CardTitle className="text-base">{review.published_academic_summary.length} recent results</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground">Financial records are not included in the admission packet.</CardContent></Card>
        </div>

        <div>
          <h3 className="mb-3 font-semibold">Published academic summary</h3>
          {review.published_academic_summary.length === 0 ? <p className="text-sm text-muted-foreground">No published assessment results are available in the transfer packet.</p> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="border-b text-xs text-muted-foreground"><tr><th className="p-2">Date</th><th className="p-2">Subject</th><th className="p-2">Assessment</th><th className="p-2">Score</th><th className="p-2">%</th></tr></thead><tbody>{review.published_academic_summary.map((row, index) => <tr key={`${row.assessment_date}-${row.title}-${index}`} className="border-b"><td className="p-2">{row.assessment_date}</td><td className="p-2">{row.subject || "—"}</td><td className="p-2">{row.title}</td><td className="p-2">{row.is_absent ? "Absent" : row.score == null ? "—" : `${row.score}/${row.max_score}`}</td><td className="p-2">{row.percentage == null ? "—" : `${row.percentage}%`}</td></tr>)}</tbody></table></div>}
        </div>

        {review.transfer.status === "under_review" && <div className="grid gap-6 border-t pt-5 xl:grid-cols-2">
          <form onSubmit={accept} className="space-y-4 rounded-xl border p-4">
            <div><h3 className="font-semibold">Accept learner</h3><p className="mt-1 text-xs text-muted-foreground">Acceptance is the final action that closes the source enrolment and activates this school's enrolment.</p></div>
            <div className="grid gap-1.5"><Label>Receiving class</Label><select className="h-9 w-full rounded-md border bg-transparent px-3 text-sm" value={acceptForm.class_id} onChange={(e) => setAcceptForm((v) => ({ ...v, class_id: e.target.value }))} required><option value="">Select class</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div>
            <div className="grid gap-1.5"><Label>Effective start date</Label><Input type="date" value={acceptForm.start_date} onChange={(e) => setAcceptForm((v) => ({ ...v, start_date: e.target.value }))} required /></div>
            <div className="grid gap-1.5"><Label>Admission / placement note</Label><Input value={acceptForm.destination_note} onChange={(e) => setAcceptForm((v) => ({ ...v, destination_note: e.target.value }))} placeholder="Optional receiving-school note" /></div>
            <label className="flex items-start gap-3 rounded-lg border p-3 text-sm"><input className="mt-1" type="checkbox" checked={acceptForm.records_verified} onChange={(e) => setAcceptForm((v) => ({ ...v, records_verified: e.target.checked }))} /><span><span className="font-medium">Transfer packet reviewed</span><span className="mt-1 block text-xs text-muted-foreground">I confirm the receiving school reviewed the learner identity, placement, attendance and published academic information shown above.</span></span></label>
            <Button type="submit" disabled={saving || !acceptForm.class_id || !acceptForm.records_verified}><CheckCircle2 className="mr-2 h-4 w-4" />Accept and activate enrolment</Button>
          </form>

          <div className="space-y-4 rounded-xl border p-4">
            <div><h3 className="font-semibold">Reject transfer application</h3><p className="mt-1 text-xs text-muted-foreground">Rejection closes this transfer case but leaves the learner's source-school enrolment unchanged.</p></div>
            <div className="grid gap-1.5"><Label>Reason for rejection</Label><Input value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} placeholder="Provide a clear admission decision reason" /></div>
            <Button variant="outline" disabled={saving || rejectReason.trim().length < 3} onClick={() => void reject()}><XCircle className="mr-2 h-4 w-4" />Reject transfer</Button>
          </div>
        </div>}

        <div className="rounded-lg border bg-muted/20 p-4 text-xs text-muted-foreground">Review access is limited to the transfer case. Full longitudinal academic/attendance history unlocks after acceptance. Financial records are never included, and the receiving school cannot edit source-school records.</div>
      </div>}

      {dossier && <div className="space-y-5 rounded-2xl border bg-card p-6">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div><div className="flex items-center gap-2 text-sm text-muted-foreground"><ShieldCheck className="h-4 w-4" />Accepted transfer · read-only historical record</div><h2 className="mt-1 text-2xl font-bold">{dossier.learner.first_name} {dossier.learner.last_name}</h2><p className="text-sm text-muted-foreground">{dossier.transfer.reference_number} · Admission #{dossier.learner.admission_number} · {dossier.learner.nationality || "Nationality not set"}</p></div>
          <Button variant="outline" onClick={() => setDossier(null)}>Close record</Button>
        </div>

        <div className="grid gap-3 md:grid-cols-3">{dossier.shared_source_schools.map((school) => <div key={school.school_id} className="rounded-lg border p-3"><div className="flex items-center gap-2 text-sm font-medium"><School className="h-4 w-4" />{school.school || "Previous school"}</div><div className="mt-1 text-xs text-muted-foreground">Historical records shared through accepted transfer lineage</div></div>)}</div>

        <div>
          <h3 className="mb-3 font-semibold">Enrolment history</h3>
          <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="border-b text-xs text-muted-foreground"><tr><th className="p-2">School</th><th className="p-2">Class</th><th className="p-2">Year / term</th><th className="p-2">Dates</th><th className="p-2">Status</th></tr></thead><tbody>{dossier.enrollments.map((row) => <tr key={row.id} className="border-b"><td className="p-2">{row.school}</td><td className="p-2">{row.class?.grade} {row.class?.name}</td><td className="p-2">{row.academic_year || "—"} / {row.term || "—"}</td><td className="p-2">{row.start_date || "—"} → {row.end_date || "Current"}</td><td className="p-2">{row.status}</td></tr>)}</tbody></table></div>
        </div>

        <div>
          <h3 className="mb-3 font-semibold">Published academic history</h3>
          {dossier.academic_history.length === 0 ? <p className="text-sm text-muted-foreground">No published assessment records are available from the previous school history.</p> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="border-b text-xs text-muted-foreground"><tr><th className="p-2">School</th><th className="p-2">Term</th><th className="p-2">Subject</th><th className="p-2">Assessment</th><th className="p-2">Score</th><th className="p-2">%</th></tr></thead><tbody>{dossier.academic_history.map((row) => <tr key={`${row.assessment_id}-${row.school_id}`} className="border-b"><td className="p-2">{row.school}</td><td className="p-2">{row.academic_year} · {row.term}</td><td className="p-2">{row.subject}</td><td className="p-2">{row.title}</td><td className="p-2">{row.is_absent ? "Absent" : row.score == null ? "—" : `${row.score}/${row.max_score}`}</td><td className="p-2">{row.percentage == null ? "—" : `${row.percentage}%`}</td></tr>)}</tbody></table></div>}
        </div>

        <div>
          <h3 className="mb-3 font-semibold">Attendance history</h3>
          {dossier.attendance.length === 0 ? <p className="text-sm text-muted-foreground">No historical attendance records are available.</p> : <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{dossier.attendance.slice(-90).reverse().map((row) => <div key={row.id} className="rounded-lg border p-3 text-sm"><div className="font-medium">{row.date} · {row.status}</div><div className="mt-1 text-xs text-muted-foreground">{row.school} · {row.academic_year || "Year not tagged"} · {row.term || "Term not tagged"}</div>{row.remarks && <div className="mt-2 text-xs">{row.remarks}</div>}</div>)}</div>}
        </div>

        <div className="rounded-lg border bg-muted/20 p-4 text-xs text-muted-foreground">Financial records are not shared through learner transfer. The receiving school can read historical academic/attendance records but cannot edit or delete source-school records.</div>
      </div>}
    </div>
  )
}
