"use client"

import * as React from "react"
import { BookOpen, CheckCircle2, ClipboardCheck, Loader2, Send, Upload } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAppData } from "@/provider/dataProvider"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"
import { getCurriculumCatalog, type CurriculumCatalog } from "@/api/academic"
import { createAssignment, createLesson, getAssignmentSubmissions, getAssignments, getLessons, gradeSubmission, publishAssignment, publishLesson, submitAssignment, type Assignment, type Lesson, type Submission } from "@/api/lms"

const WRITER_ROLES = ["school_admin", "principal", "vice_principal", "teacher", "class_teacher"]

type Tab = "lessons" | "assignments" | "marking"

export default function LearningCenterPage() {
  const { classes } = useAppData()
  const { workspace } = useSchoolWorkspace()
  const role = workspace?.role ?? ""
  const canWrite = Boolean(workspace?.is_platform_admin) || WRITER_ROLES.includes(role)
  const isStudent = role === "student"
  const [tab, setTab] = React.useState<Tab>("lessons")
  const [catalog, setCatalog] = React.useState<CurriculumCatalog | null>(null)
  const [lessons, setLessons] = React.useState<Lesson[]>([])
  const [assignments, setAssignments] = React.useState<Assignment[]>([])
  const [submissions, setSubmissions] = React.useState<Submission[]>([])
  const [selectedAssignment, setSelectedAssignment] = React.useState<Assignment | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [message, setMessage] = React.useState<string | null>(null)
  const [answers, setAnswers] = React.useState<Record<string, string>>({})
  const [scores, setScores] = React.useState<Record<string, string>>({})
  const [feedback, setFeedback] = React.useState<Record<string, string>>({})
  const [lessonForm, setLessonForm] = React.useState({ class_id: "", subject_id: "", title: "", summary: "", body: "", resource_url: "" })
  const [assignmentForm, setAssignmentForm] = React.useState({ class_id: "", subject_id: "", title: "", instructions: "", due_at: "", max_score: 100 })

  const refresh = React.useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [nextLessons, nextAssignments, nextCatalog] = await Promise.all([getLessons(), getAssignments(), getCurriculumCatalog()])
      setLessons(nextLessons); setAssignments(nextAssignments); setCatalog(nextCatalog)
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to load learning center") }
    finally { setLoading(false) }
  }, [])
  React.useEffect(() => { void refresh() }, [workspace?.school.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (action: () => Promise<unknown>, success: string) => {
    setSaving(true); setError(null); setMessage(null)
    try { await action(); setMessage(success); await refresh() }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to save learning work") }
    finally { setSaving(false) }
  }

  const openMarking = async (assignment: Assignment) => {
    setSaving(true); setError(null)
    try { setSelectedAssignment(assignment); setSubmissions(await getAssignmentSubmissions(assignment.id)); setTab("marking") }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to load submissions") }
    finally { setSaving(false) }
  }

  if (loading) return <div className="flex min-h-[55vh] items-center justify-center gap-3 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" />Loading Learning Center…</div>

  return <div className="space-y-6">
    <div className="rounded-2xl border bg-card p-6"><div className="flex items-center gap-2 text-sm font-medium text-muted-foreground"><BookOpen className="h-4 w-4" />Daily teaching and learning</div><h1 className="mt-2 text-3xl font-bold tracking-tight">Learning Center</h1><p className="mt-2 max-w-3xl text-sm text-muted-foreground">Teachers publish lessons and assignments; learners submit work; teachers mark it and the learner receives a central !thute Push notification when marking is complete.</p></div>
    {error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}
    {message && <div className="rounded-lg border p-3 text-sm"><CheckCircle2 className="mr-2 inline h-4 w-4" />{message}</div>}
    <div className="flex flex-wrap gap-2"><Button variant={tab === "lessons" ? "default" : "outline"} onClick={() => setTab("lessons")}>Lessons</Button><Button variant={tab === "assignments" ? "default" : "outline"} onClick={() => setTab("assignments")}>Assignments</Button>{canWrite && <Button variant={tab === "marking" ? "default" : "outline"} onClick={() => setTab("marking")}>Marking</Button>}</div>

    {tab === "lessons" && <div className={`grid gap-6 ${canWrite ? "xl:grid-cols-[minmax(0,1fr)_400px]" : ""}`}><Card><CardHeader><CardTitle>Lessons</CardTitle><CardDescription>{isStudent ? "Published lessons for your school workspace." : "Draft, publish and archive-ready lesson records."}</CardDescription></CardHeader><CardContent className="space-y-3">{lessons.length === 0 ? <div className="py-8 text-center text-sm text-muted-foreground">No lessons yet.</div> : lessons.map((item) => <div key={item.id} className="rounded-xl border p-4"><div className="flex items-start justify-between gap-3"><div><div className="font-semibold">{item.title}</div><div className="mt-1 text-sm text-muted-foreground">{item.summary || "No summary"}</div>{item.body && <div className="mt-3 whitespace-pre-wrap text-sm">{item.body}</div>}{item.resource_url && <a className="mt-2 block text-sm underline" href={item.resource_url} target="_blank" rel="noreferrer">Open resource</a>}</div><div className="text-xs font-medium">{item.status}</div></div>{canWrite && item.status === "draft" && <Button className="mt-3" size="sm" disabled={saving} onClick={() => void run(() => publishLesson(item.id), "Lesson published")}>Publish lesson</Button>}</div>)}</CardContent></Card>{canWrite && <Card><CardHeader><CardTitle>Create lesson</CardTitle></CardHeader><CardContent className="space-y-3"><div className="grid gap-1.5"><Label>Class</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={lessonForm.class_id} onChange={(e) => setLessonForm((v) => ({ ...v, class_id: e.target.value }))}><option value="">Select class</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div><div className="grid gap-1.5"><Label>Subject</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={lessonForm.subject_id} onChange={(e) => setLessonForm((v) => ({ ...v, subject_id: e.target.value }))}><option value="">Select subject</option>{catalog?.subjects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div><div className="grid gap-1.5"><Label>Title</Label><Input value={lessonForm.title} onChange={(e) => setLessonForm((v) => ({ ...v, title: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Summary</Label><Input value={lessonForm.summary} onChange={(e) => setLessonForm((v) => ({ ...v, summary: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Lesson content</Label><textarea className="min-h-28 rounded-md border bg-transparent p-3 text-sm" value={lessonForm.body} onChange={(e) => setLessonForm((v) => ({ ...v, body: e.target.value }))} /></div><Button disabled={saving || !lessonForm.class_id || !lessonForm.subject_id || !lessonForm.title} onClick={() => void run(() => createLesson(lessonForm), "Lesson saved as draft")}>Save lesson</Button></CardContent></Card>}</div>}

    {tab === "assignments" && <div className={`grid gap-6 ${canWrite ? "xl:grid-cols-[minmax(0,1fr)_400px]" : ""}`}><Card><CardHeader><CardTitle>Assignments</CardTitle></CardHeader><CardContent className="space-y-3">{assignments.length === 0 ? <div className="py-8 text-center text-sm text-muted-foreground">No assignments.</div> : assignments.map((item) => <div key={item.id} className="rounded-xl border p-4"><div className="flex items-start justify-between gap-3"><div><div className="font-semibold">{item.title}</div><div className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">{item.instructions}</div><div className="mt-2 text-xs text-muted-foreground">{item.due_at ? `Due ${new Date(item.due_at).toLocaleString()}` : "No deadline"} · {item.max_score} marks</div></div><div className="text-xs font-medium">{item.status}</div></div>{canWrite && <div className="mt-3 flex gap-2">{item.status === "draft" && <Button size="sm" disabled={saving} onClick={() => void run(() => publishAssignment(item.id), "Assignment published and learners notified")}>Publish</Button>}<Button size="sm" variant="outline" disabled={saving} onClick={() => void openMarking(item)}><ClipboardCheck className="mr-2 h-4 w-4" />Submissions</Button></div>}{isStudent && item.status === "published" && <div className="mt-4 space-y-2"><textarea className="min-h-24 w-full rounded-md border bg-transparent p-3 text-sm" placeholder="Write your answer or submission note…" value={answers[item.id] || ""} onChange={(e) => setAnswers((v) => ({ ...v, [item.id]: e.target.value }))} /><Button size="sm" disabled={saving || !(answers[item.id] || "").trim()} onClick={() => void run(() => submitAssignment(item.id, { answer_text: answers[item.id] }), "Assignment submitted") }><Send className="mr-2 h-4 w-4" />Submit work</Button></div>}</div>)}</CardContent></Card>{canWrite && <Card><CardHeader><CardTitle>Create assignment</CardTitle></CardHeader><CardContent className="space-y-3"><div className="grid gap-1.5"><Label>Class</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={assignmentForm.class_id} onChange={(e) => setAssignmentForm((v) => ({ ...v, class_id: e.target.value }))}><option value="">Select class</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div><div className="grid gap-1.5"><Label>Subject</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={assignmentForm.subject_id} onChange={(e) => setAssignmentForm((v) => ({ ...v, subject_id: e.target.value }))}><option value="">Select subject</option>{catalog?.subjects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div><div className="grid gap-1.5"><Label>Title</Label><Input value={assignmentForm.title} onChange={(e) => setAssignmentForm((v) => ({ ...v, title: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Instructions</Label><textarea className="min-h-24 rounded-md border bg-transparent p-3 text-sm" value={assignmentForm.instructions} onChange={(e) => setAssignmentForm((v) => ({ ...v, instructions: e.target.value }))} /></div><div className="grid grid-cols-2 gap-3"><div className="grid gap-1.5"><Label>Due</Label><Input type="datetime-local" value={assignmentForm.due_at} onChange={(e) => setAssignmentForm((v) => ({ ...v, due_at: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Max score</Label><Input type="number" min={1} value={assignmentForm.max_score} onChange={(e) => setAssignmentForm((v) => ({ ...v, max_score: Number(e.target.value) }))} /></div></div><Button disabled={saving || !assignmentForm.class_id || !assignmentForm.subject_id || !assignmentForm.title || !assignmentForm.instructions} onClick={() => void run(() => createAssignment({ ...assignmentForm, due_at: assignmentForm.due_at ? new Date(assignmentForm.due_at).toISOString() : null }), "Assignment saved as draft")}>Save assignment</Button></CardContent></Card>}</div>}

    {tab === "marking" && canWrite && <Card><CardHeader><CardTitle>Mark submissions</CardTitle><CardDescription>{selectedAssignment ? selectedAssignment.title : "Open an assignment from the Assignments tab to load its submissions."}</CardDescription></CardHeader><CardContent className="space-y-3">{!selectedAssignment ? <div className="py-8 text-center text-sm text-muted-foreground">No assignment selected.</div> : submissions.length === 0 ? <div className="py-8 text-center text-sm text-muted-foreground">No submissions yet.</div> : submissions.map((item) => <div key={item.id} className="rounded-xl border p-4"><div className="text-xs font-semibold text-muted-foreground">LEARNER {item.student_id.slice(0, 8)} · ATTEMPT {item.attempt_no}</div><div className="mt-2 whitespace-pre-wrap text-sm">{item.answer_text || "Attachment-only submission"}</div>{item.attachment_url && <a className="mt-2 block text-sm underline" href={item.attachment_url} target="_blank" rel="noreferrer"><Upload className="mr-1 inline h-3.5 w-3.5" />Open attachment</a>}<div className="mt-4 grid gap-3 md:grid-cols-[120px_minmax(0,1fr)_auto]"><Input type="number" min={0} max={Number(selectedAssignment.max_score)} placeholder="Score" value={scores[item.id] || ""} onChange={(e) => setScores((v) => ({ ...v, [item.id]: e.target.value }))} /><Input placeholder="Feedback" value={feedback[item.id] || ""} onChange={(e) => setFeedback((v) => ({ ...v, [item.id]: e.target.value }))} /><Button disabled={saving || scores[item.id] === undefined || scores[item.id] === ""} onClick={() => void run(async () => { await gradeSubmission(item.id, { score: Number(scores[item.id]), feedback: feedback[item.id] }); setSubmissions(await getAssignmentSubmissions(selectedAssignment.id)) }, "Submission marked and learner notified")}>Save mark</Button></div></div>)}</CardContent></Card>}
  </div>
}
