"use client"

import * as React from "react"
import { BookOpenCheck, Brain, ClipboardCheck, Loader2, Sparkles, Target, Users } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { generateStudyPlan, getMyPortal, getMyTutor, getPracticeQuestions, type PortalSnapshot, type PracticeQuestion, type TutorProfile } from "@/api/tutor"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"

function masteryNumber(value: number | string) { return Math.max(0, Math.min(100, Number(value || 0))) }

export default function TutorDashboardPage() {
  const { workspace } = useSchoolWorkspace()
  const [portal, setPortal] = React.useState<PortalSnapshot | null>(null)
  const [tutor, setTutor] = React.useState<TutorProfile | null>(null)
  const [practice, setPractice] = React.useState<PracticeQuestion[]>([])
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [message, setMessage] = React.useState<string | null>(null)

  const refresh = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const snapshot = await getMyPortal()
      setPortal(snapshot)
      if (snapshot.portal === "student") setTutor(await getMyTutor())
      else setTutor(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load Tutor")
    } finally { setLoading(false) }
  }, [])

  React.useEffect(() => { void refresh() }, [workspace?.school.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const buildPlan = async () => {
    if (!tutor) return
    setSaving(true); setError(null); setMessage(null)
    try {
      await generateStudyPlan(tutor.student_id)
      setMessage("A new study plan was created from your weak topics and current assignments.")
      await refresh()
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to generate study plan") }
    finally { setSaving(false) }
  }

  const startPractice = async () => {
    if (!tutor) return
    setSaving(true); setError(null); setMessage(null)
    try { setPractice(await getPracticeQuestions(tutor.student_id, 10)) }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to prepare practice") }
    finally { setSaving(false) }
  }

  if (loading) return <div className="flex min-h-[55vh] items-center justify-center gap-3 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" />Loading your Tutor…</div>

  return <div className="space-y-6">
    <div className="rounded-2xl border bg-card p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground"><Sparkles className="h-4 w-4" />Personalised learning workspace</div>
          <h1 className="text-3xl font-bold tracking-tight">!thute Tutor</h1>
          <p className="mt-2 max-w-3xl text-sm text-muted-foreground">The same learner identity keeps its mastery history when changing schools. Current assignments come from this school; learning strengths and gaps follow the learner.</p>
        </div>
        <Button variant="outline" onClick={() => void refresh()}>Refresh</Button>
      </div>
    </div>

    {error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}
    {message && <div className="rounded-lg border p-3 text-sm">{message}</div>}

    {portal?.portal === "student" && tutor && <>
      <div className="grid gap-4 md:grid-cols-4">
        <Card><CardHeader className="pb-2"><CardDescription>Weak topics</CardDescription><CardTitle className="text-3xl">{tutor.weak_topics.length}</CardTitle></CardHeader></Card>
        <Card><CardHeader className="pb-2"><CardDescription>Current assignments</CardDescription><CardTitle className="text-3xl">{tutor.assignments.length}</CardTitle></CardHeader></Card>
        <Card><CardHeader className="pb-2"><CardDescription>Mastery topics</CardDescription><CardTitle className="text-3xl">{tutor.mastery.length}</CardTitle></CardHeader></Card>
        <Card><CardHeader className="pb-2"><CardDescription>Active study plans</CardDescription><CardTitle className="text-3xl">{portal.study_plans.length}</CardTitle></CardHeader></Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Target className="h-5 w-5" />Mastery map</CardTitle><CardDescription>Lowest mastery appears first so revision focuses on the biggest learning gaps.</CardDescription></CardHeader>
          <CardContent className="space-y-4">
            {tutor.mastery.length === 0 ? <div className="py-8 text-center text-sm text-muted-foreground">No mastery evidence yet. Complete marked work or online quizzes to build the learner profile.</div> : tutor.mastery.slice(0, 16).map((item) => {
              const score = masteryNumber(item.mastery_score)
              return <div key={item.id} className="space-y-1.5"><div className="flex justify-between gap-3 text-sm"><span className="font-medium">{item.topic_key}</span><span>{score.toFixed(0)}%</span></div><div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full bg-foreground" style={{ width: `${score}%` }} /></div></div>
            })}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card><CardHeader><CardTitle className="flex items-center gap-2"><Brain className="h-5 w-5" />What should I do next?</CardTitle></CardHeader><CardContent className="space-y-3">{tutor.recommended_modes.map((item) => <div key={item.mode} className="rounded-lg border p-3"><div className="font-medium capitalize">{item.mode}</div><div className="mt-1 text-xs text-muted-foreground">{item.reason}</div></div>)}<div className="grid grid-cols-2 gap-2"><Button disabled={saving} onClick={() => void buildPlan()}>Make plan</Button><Button disabled={saving} variant="outline" onClick={() => void startPractice()}>Practice</Button></div></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-base">Current assignments</CardTitle></CardHeader><CardContent className="space-y-2">{tutor.assignments.slice(0, 6).map((item) => <div key={item.id} className="rounded-lg border p-3 text-sm"><div className="font-medium">{item.title}</div><div className="mt-1 text-xs text-muted-foreground">{item.due_at ? `Due ${new Date(item.due_at).toLocaleString()}` : "No due date"}</div></div>)}{tutor.assignments.length === 0 && <div className="text-sm text-muted-foreground">No published assignments.</div>}</CardContent></Card>
        </div>
      </div>

      {practice.length > 0 && <Card><CardHeader><CardTitle className="flex items-center gap-2"><BookOpenCheck className="h-5 w-5" />Tutor practice set</CardTitle><CardDescription>Questions are selected from weak topics first. Correct answers are never sent in this practice payload.</CardDescription></CardHeader><CardContent className="space-y-4">{practice.map((question, index) => <div key={question.id} className="rounded-xl border p-4"><div className="text-xs font-semibold text-muted-foreground">QUESTION {index + 1} · {question.topic_key || "General"}</div><div className="mt-2 font-medium">{question.prompt}</div>{question.choices?.length ? <div className="mt-3 grid gap-2">{question.choices.map((choice) => <div key={choice} className="rounded-lg border px-3 py-2 text-sm">{choice}</div>)}</div> : null}</div>)}</CardContent></Card>}
    </>}

    {portal?.portal === "parent" && <Card><CardHeader><CardTitle className="flex items-center gap-2"><Users className="h-5 w-5" />Parent portal</CardTitle><CardDescription>See current schoolwork, results and learning progress for linked children.</CardDescription></CardHeader><CardContent className="grid gap-4 lg:grid-cols-2">{portal.children.map((child) => <div key={child.student_id} className="rounded-xl border p-4"><div className="font-semibold">Learner {child.student_id.slice(0, 8)}</div><div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs"><div className="rounded-lg bg-muted p-2"><div className="text-lg font-bold">{child.assignments.length}</div>Assignments</div><div className="rounded-lg bg-muted p-2"><div className="text-lg font-bold">{child.results.length}</div>Results</div><div className="rounded-lg bg-muted p-2"><div className="text-lg font-bold">{child.mastery.length}</div>Topics</div></div></div>)}</CardContent></Card>}

    {portal?.portal === "teacher" && <div className="grid gap-4 md:grid-cols-2"><Card><CardHeader><CardDescription>Teaching assignments</CardDescription><CardTitle className="text-4xl">{portal.teaching_assignments.length}</CardTitle></CardHeader></Card><Card><CardHeader><CardDescription>Waiting for marking</CardDescription><CardTitle className="text-4xl">{portal.pending_marking.length}</CardTitle></CardHeader><CardContent><div className="flex items-center gap-2 text-sm text-muted-foreground"><ClipboardCheck className="h-4 w-4" />Open submissions from your published assignments.</div></CardContent></Card></div>}

    {portal?.portal === "management" && <div className="grid gap-4 md:grid-cols-2"><Card><CardHeader><CardDescription>Active learners</CardDescription><CardTitle className="text-4xl">{portal.active_students}</CardTitle></CardHeader></Card><Card><CardHeader><CardDescription>Pending assignment submissions</CardDescription><CardTitle className="text-4xl">{portal.pending_submissions}</CardTitle></CardHeader></Card></div>}
  </div>
}
