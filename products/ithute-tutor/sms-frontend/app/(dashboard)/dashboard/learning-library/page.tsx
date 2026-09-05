"use client"

import * as React from "react"
import { BookOpen, CheckCircle2, ExternalLink, Loader2, Plus, School, ShieldCheck } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { getCurriculumCatalog, type CurriculumCatalog } from "@/api/academic"
import {
  archiveLearningMaterial,
  createLearningMaterial,
  getPeerReviewQueue,
  getPlatformReviewQueue,
  getSchoolLearningMaterials,
  getSharedLearningLibrary,
  peerApproveLearningMaterial,
  platformModerateLearningMaterial,
  submitLearningMaterial,
  type LearningMaterial,
} from "@/api/learning"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"

type View = "library" | "school" | "review"

const AUTHOR_ROLES = ["school_admin", "principal", "vice_principal", "teacher", "class_teacher"]
const REVIEW_ROLES = ["school_admin", "principal", "vice_principal"]

function badge(status: string) {
  const labels: Record<string, string> = {
    draft: "Draft",
    pending: "Awaiting approval",
    approved: "Approved public",
    rejected: "Rejected",
    archived: "Archived",
  }
  return labels[status] ?? status
}

function MaterialCard({ material, actions }: { material: LearningMaterial; actions?: React.ReactNode }) {
  return (
    <Card className="h-full">
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <School className="h-3.5 w-3.5" />{material.source_school || "School"}
          </div>
          <span className="rounded-full border px-2 py-1 text-[11px] font-medium">{badge(material.moderation_status)}</span>
        </div>
        <div>
          <CardTitle className="text-lg">{material.title}</CardTitle>
          <CardDescription className="mt-1">{material.description || "No description provided."}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          {material.grade && <span className="rounded-md bg-muted px-2 py-1">{material.grade}</span>}
          {material.subject && <span className="rounded-md bg-muted px-2 py-1">{material.subject}</span>}
          <span className="rounded-md bg-muted px-2 py-1">{material.content_type}</span>
          {material.visibility === "public" && <span className="rounded-md bg-muted px-2 py-1">Public</span>}
        </div>
        {material.body && <div className="whitespace-pre-wrap rounded-lg border bg-muted/20 p-3 text-sm leading-6">{material.body}</div>}
        {material.resource_url && (
          <a className="inline-flex items-center gap-2 text-sm font-medium underline underline-offset-4" href={material.resource_url} target="_blank" rel="noreferrer">
            Open learning resource <ExternalLink className="h-4 w-4" />
          </a>
        )}
        {material.moderation_status === "approved" && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <ShieldCheck className="h-4 w-4" />
            Approved by {material.approval_source === "platform" ? "!thute Tutor" : `${material.peer_approval_count} peer school${material.peer_approval_count === 1 ? "" : "s"}`}
          </div>
        )}
        {actions && <div className="flex flex-wrap gap-2 border-t pt-3">{actions}</div>}
      </CardContent>
    </Card>
  )
}

export default function LearningLibraryPage() {
  const { workspace } = useSchoolWorkspace()
  const role = workspace?.role ?? ""
  const isPlatformAdmin = Boolean(workspace?.is_platform_admin)
  const canAuthor = isPlatformAdmin || AUTHOR_ROLES.includes(role)
  const canPeerReview = !isPlatformAdmin && REVIEW_ROLES.includes(role)
  const canReview = isPlatformAdmin || canPeerReview

  const [view, setView] = React.useState<View>("library")
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [library, setLibrary] = React.useState<LearningMaterial[]>([])
  const [mine, setMine] = React.useState<LearningMaterial[]>([])
  const [review, setReview] = React.useState<LearningMaterial[]>([])
  const [catalog, setCatalog] = React.useState<CurriculumCatalog | null>(null)
  const [search, setSearch] = React.useState("")
  const [form, setForm] = React.useState({
    title: "",
    description: "",
    content_type: "note" as LearningMaterial["content_type"],
    body: "",
    resource_url: "",
    grade_id: "",
    subject_id: "",
    visibility: "public" as "school" | "public",
    peer_approval_threshold: 1,
  })

  const refresh = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [nextLibrary, nextMine, nextCatalog] = await Promise.all([
        getSharedLearningLibrary(search.trim() ? { q: search.trim() } : undefined),
        getSchoolLearningMaterials(),
        getCurriculumCatalog(),
      ])
      setLibrary(nextLibrary)
      setMine(nextMine)
      if (canReview) {
        try {
          setReview(isPlatformAdmin ? await getPlatformReviewQueue() : await getPeerReviewQueue())
        } catch {
          setReview([])
        }
      } else {
        setReview([])
      }
      setCatalog(nextCatalog)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load the learning exchange")
    } finally {
      setLoading(false)
    }
  }, [canReview, isPlatformAdmin, search])

  React.useEffect(() => { void refresh() }, [workspace?.school.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const createMaterial = async (event: React.FormEvent) => {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await createLearningMaterial({
        title: form.title,
        description: form.description || null,
        content_type: form.content_type,
        body: form.body || null,
        resource_url: form.resource_url || null,
        grade_id: form.grade_id || null,
        subject_id: form.subject_id || null,
        visibility: form.visibility,
        peer_approval_threshold: form.peer_approval_threshold,
      })
      setForm((current) => ({ ...current, title: "", description: "", body: "", resource_url: "" }))
      setView("school")
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create learning material")
    } finally {
      setSaving(false)
    }
  }

  const runAction = async (action: () => Promise<unknown>) => {
    setSaving(true)
    setError(null)
    try {
      await action()
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update learning material")
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="flex min-h-[55vh] items-center justify-center gap-3 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" />Loading shared learning library…</div>
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border bg-card p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground"><BookOpen className="h-4 w-4" />Cross-school knowledge exchange</div>
            <h1 className="text-3xl font-bold tracking-tight">!thute Learning Library</h1>
            <p className="mt-2 max-w-3xl text-sm text-muted-foreground">Schools keep ownership of their material. Public resources become visible to learners in other schools only after !thute Tutor or independent peer-school approval.</p>
          </div>
          <Button variant="outline" onClick={() => void refresh()}>Refresh</Button>
        </div>
      </div>

      {error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}

      <div className="flex flex-wrap gap-2">
        <Button variant={view === "library" ? "default" : "outline"} onClick={() => setView("library")}>Shared library ({library.length})</Button>
        <Button variant={view === "school" ? "default" : "outline"} onClick={() => setView("school")}>My school material ({mine.length})</Button>
        {canReview && <Button variant={view === "review" ? "default" : "outline"} onClick={() => setView("review")}>Approval queue ({review.length})</Button>}
      </div>

      {view === "library" && (
        <div className="space-y-4">
          <div className="flex max-w-xl gap-2"><Input placeholder="Search approved public material…" value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void refresh() }} /><Button variant="outline" onClick={() => void refresh()}>Search</Button></div>
          {library.length === 0 ? <Card><CardContent className="p-8 text-center text-sm text-muted-foreground">No approved public material matches this view yet.</CardContent></Card> : <div className="grid gap-4 lg:grid-cols-2">{library.map((item) => <MaterialCard key={item.id} material={item} />)}</div>}
        </div>
      )}

      {view === "school" && (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
          <div className="space-y-4">
            {mine.length === 0 ? <Card><CardContent className="p-8 text-center text-sm text-muted-foreground">This school has not created learning material yet.</CardContent></Card> : <div className="grid gap-4 lg:grid-cols-2">{mine.map((item) => <MaterialCard key={item.id} material={item} actions={<>{item.visibility === "public" && ["draft", "rejected"].includes(item.moderation_status) && canAuthor && <Button size="sm" disabled={saving} onClick={() => void runAction(() => submitLearningMaterial(item.id))}><ShieldCheck className="mr-2 h-4 w-4" />Submit for approval</Button>}{item.moderation_status !== "archived" && canAuthor && <Button size="sm" variant="outline" disabled={saving} onClick={() => void runAction(() => archiveLearningMaterial(item.id))}>Archive</Button>}</>} />)}</div>}
          </div>

          {canAuthor && <Card>
            <CardHeader><CardTitle>Publish learning material</CardTitle><CardDescription>Create school-only material or submit it to the shared Tutor library.</CardDescription></CardHeader>
            <CardContent><form className="space-y-4" onSubmit={createMaterial}>
              <div className="grid gap-1.5"><Label>Title</Label><Input value={form.title} onChange={(e) => setForm((v) => ({ ...v, title: e.target.value }))} required /></div>
              <div className="grid gap-1.5"><Label>Description</Label><Input value={form.description} onChange={(e) => setForm((v) => ({ ...v, description: e.target.value }))} /></div>
              <div className="grid gap-1.5"><Label>Material type</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={form.content_type} onChange={(e) => setForm((v) => ({ ...v, content_type: e.target.value as LearningMaterial["content_type"] }))}>{["note", "document", "link", "video", "worksheet", "lesson", "other"].map((type) => <option key={type} value={type}>{type}</option>)}</select></div>
              <div className="grid gap-1.5"><Label>Learning content</Label><textarea className="min-h-28 rounded-md border bg-transparent p-3 text-sm" value={form.body} onChange={(e) => setForm((v) => ({ ...v, body: e.target.value }))} placeholder="Write the lesson, notes, instructions or summary here…" /></div>
              <div className="grid gap-1.5"><Label>Resource URL (optional)</Label><Input type="url" value={form.resource_url} onChange={(e) => setForm((v) => ({ ...v, resource_url: e.target.value }))} placeholder="https://…" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div className="grid gap-1.5"><Label>Grade</Label><select className="h-9 rounded-md border bg-transparent px-2 text-sm" value={form.grade_id} onChange={(e) => setForm((v) => ({ ...v, grade_id: e.target.value }))}><option value="">All</option>{catalog?.grades.map((grade) => <option key={grade.id} value={grade.id}>{grade.name}</option>)}</select></div>
                <div className="grid gap-1.5"><Label>Subject</Label><select className="h-9 rounded-md border bg-transparent px-2 text-sm" value={form.subject_id} onChange={(e) => setForm((v) => ({ ...v, subject_id: e.target.value }))}><option value="">General</option>{catalog?.subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}</select></div>
              </div>
              <div className="grid gap-1.5"><Label>Visibility</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={form.visibility} onChange={(e) => setForm((v) => ({ ...v, visibility: e.target.value as "school" | "public" }))}><option value="school">My school only</option><option value="public">Public after approval</option></select></div>
              {form.visibility === "public" && <div className="grid gap-1.5"><Label>Peer schools required for approval</Label><Input type="number" min={1} max={20} value={form.peer_approval_threshold} onChange={(e) => setForm((v) => ({ ...v, peer_approval_threshold: Number(e.target.value) }))} /></div>}
              <Button className="w-full" type="submit" disabled={saving}><Plus className="mr-2 h-4 w-4" />Create material</Button>
            </form></CardContent>
          </Card>}
        </div>
      )}

      {view === "review" && canReview && (
        <div className="space-y-4">
          <div className="rounded-lg border bg-muted/20 p-4 text-sm text-muted-foreground">{isPlatformAdmin ? "Platform review can approve or reject material for the whole Tutor network." : "Your school can independently approve material submitted by another school. The publishing school cannot approve itself."}</div>
          {review.length === 0 ? <Card><CardContent className="p-8 text-center text-sm text-muted-foreground">No public material is waiting for this review queue.</CardContent></Card> : <div className="grid gap-4 lg:grid-cols-2">{review.map((item) => <MaterialCard key={item.id} material={item} actions={isPlatformAdmin ? <><Button size="sm" disabled={saving} onClick={() => void runAction(() => platformModerateLearningMaterial(item.id, "approved"))}><CheckCircle2 className="mr-2 h-4 w-4" />Approve</Button><Button size="sm" variant="destructive" disabled={saving} onClick={() => void runAction(() => platformModerateLearningMaterial(item.id, "rejected"))}>Reject</Button></> : <Button size="sm" disabled={saving} onClick={() => void runAction(() => peerApproveLearningMaterial(item.id))}><CheckCircle2 className="mr-2 h-4 w-4" />Approve for Tutor library</Button>} />)}</div>}
        </div>
      )}
    </div>
  )
}
