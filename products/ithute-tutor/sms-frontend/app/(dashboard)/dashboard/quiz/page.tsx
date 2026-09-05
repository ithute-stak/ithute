"use client"

import * as React from "react"
import { CheckCircle2, ClipboardCheck, Loader2, Plus, Send } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { getAssessments, type Assessment } from "@/api/academic"
import {
  addQuizQuestion,
  getAvailableQuizzes,
  getQuiz,
  getQuizAttempts,
  markQuizResponse,
  startQuizAttempt,
  submitQuizAttempt,
  type AvailableQuiz,
  type QuizDefinition,
  type QuizReviewAttempt,
} from "@/api/quiz"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"

const STAFF_ROLES = ["school_admin", "principal", "vice_principal", "teacher", "class_teacher"]

type QuestionType = "multiple_choice" | "true_false" | "short_answer" | "long_answer"

export default function OnlineQuizPage() {
  const { workspace } = useSchoolWorkspace()
  const role = workspace?.role ?? ""
  const isStudent = role === "student"
  const canManage = Boolean(workspace?.is_platform_admin) || STAFF_ROLES.includes(role)

  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [message, setMessage] = React.useState<string | null>(null)

  const [available, setAvailable] = React.useState<AvailableQuiz[]>([])
  const [assessments, setAssessments] = React.useState<Assessment[]>([])
  const [selectedId, setSelectedId] = React.useState("")
  const [quiz, setQuiz] = React.useState<QuizDefinition | null>(null)
  const [attemptId, setAttemptId] = React.useState<string | null>(null)
  const [answers, setAnswers] = React.useState<Record<string, unknown>>({})
  const [reviewAttempts, setReviewAttempts] = React.useState<QuizReviewAttempt[]>([])
  const [manualMarks, setManualMarks] = React.useState<Record<string, string>>({})

  const [question, setQuestion] = React.useState({
    topic_key: "",
    prompt: "",
    question_type: "multiple_choice" as QuestionType,
    choices: "",
    correct_answer: "",
    points: 1,
    explanation: "",
  })

  const refresh = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      if (isStudent) {
        setAvailable(await getAvailableQuizzes())
      } else if (canManage) {
        const rows = await getAssessments()
        setAssessments(rows.filter((item) => ["quiz", "test", "exam"].includes(item.assessment_type)))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load online assessments")
    } finally {
      setLoading(false)
    }
  }, [canManage, isStudent])

  React.useEffect(() => { void refresh() }, [workspace?.school.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const openStudentQuiz = async (assessmentId: string) => {
    setSaving(true); setError(null); setMessage(null)
    try {
      const [definition, attempt] = await Promise.all([getQuiz(assessmentId), startQuizAttempt(assessmentId)])
      setSelectedId(assessmentId)
      setQuiz(definition)
      setAttemptId(attempt.id)
      setAnswers({})
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to open quiz")
    } finally { setSaving(false) }
  }

  const submitStudentQuiz = async () => {
    if (!attemptId) return
    setSaving(true); setError(null); setMessage(null)
    try {
      const result = await submitQuizAttempt(attemptId, answers)
      setMessage(result.status === "graded"
        ? `Quiz graded: ${result.score ?? 0}/${result.max_score ?? 0}`
        : "Quiz submitted. A teacher will review the written responses before the final mark is released.")
      setQuiz(null); setAttemptId(null); setSelectedId("")
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to submit quiz")
    } finally { setSaving(false) }
  }

  const openStaffAssessment = async (assessmentId: string) => {
    setSaving(true); setError(null); setMessage(null)
    try {
      const [definition, attempts] = await Promise.all([getQuiz(assessmentId), getQuizAttempts(assessmentId)])
      setSelectedId(assessmentId)
      setQuiz(definition)
      setReviewAttempts(attempts)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load assessment workspace")
    } finally { setSaving(false) }
  }

  const createQuestion = async () => {
    if (!selectedId || !question.prompt.trim()) return
    setSaving(true); setError(null); setMessage(null)
    try {
      const choices = question.question_type === "multiple_choice"
        ? question.choices.split("\n").map((item) => item.trim()).filter(Boolean)
        : question.question_type === "true_false" ? ["True", "False"] : null
      await addQuizQuestion(selectedId, {
        topic_key: question.topic_key.trim() || null,
        prompt: question.prompt.trim(),
        question_type: question.question_type,
        choices,
        correct_answer: question.question_type === "long_answer" ? null : question.correct_answer,
        points: question.points,
        explanation: question.explanation.trim() || null,
      })
      setQuestion({ topic_key: "", prompt: "", question_type: "multiple_choice", choices: "", correct_answer: "", points: 1, explanation: "" })
      setMessage("Question added to assessment")
      await openStaffAssessment(selectedId)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to add question")
    } finally { setSaving(false) }
  }

  const saveManualMark = async (responseId: string) => {
    const raw = manualMarks[responseId]
    if (raw === undefined || raw === "") return
    setSaving(true); setError(null); setMessage(null)
    try {
      await markQuizResponse(responseId, Number(raw))
      setMessage("Response marked")
      if (selectedId) setReviewAttempts(await getQuizAttempts(selectedId))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save mark")
    } finally { setSaving(false) }
  }

  if (loading) return <div className="flex min-h-[55vh] items-center justify-center gap-3 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" />Loading online assessments…</div>

  return <div className="space-y-6">
    <div className="rounded-2xl border bg-card p-6">
      <p className="text-sm font-medium text-muted-foreground">Assessment delivery and marking</p>
      <h1 className="mt-2 text-3xl font-bold tracking-tight">Online Quizzes</h1>
      <p className="mt-2 max-w-3xl text-sm text-muted-foreground">Auto-mark objective questions, route written answers to teachers, update mastery evidence, and publish the final result into the normal assessment record.</p>
    </div>

    {error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}
    {message && <div className="rounded-lg border p-3 text-sm"><CheckCircle2 className="mr-2 inline h-4 w-4" />{message}</div>}

    {isStudent && <>
      {!quiz && <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {available.length === 0 ? <Card className="md:col-span-2"><CardContent className="p-8 text-center text-sm text-muted-foreground">No online quizzes are currently available for your class.</CardContent></Card> : available.map((item) => {
          const completed = item.attempt && ["needs_review", "graded"].includes(item.attempt.status)
          return <Card key={item.id}><CardHeader><CardTitle>{item.title}</CardTitle><CardDescription>{item.assessment_type} · {item.question_count} questions · {item.max_score} marks</CardDescription></CardHeader><CardContent className="space-y-3"><div className="text-sm text-muted-foreground">Assessment date: {item.assessment_date}</div>{item.attempt?.status === "graded" && <div className="rounded-lg border p-3 text-sm font-medium">Final score: {item.attempt.score ?? 0}/{item.attempt.max_score ?? item.max_score}</div>}{item.attempt?.status === "needs_review" && <div className="rounded-lg border p-3 text-sm">Submitted and waiting for teacher review.</div>}<Button disabled={saving || Boolean(completed)} onClick={() => void openStudentQuiz(item.id)}>{completed ? "Submitted" : item.attempt?.status === "in_progress" ? "Continue quiz" : "Start quiz"}</Button></CardContent></Card>
        })}
      </div>}

      {quiz && <Card><CardHeader><CardTitle>{quiz.assessment.title}</CardTitle><CardDescription>Answer every question you can. Once submitted, the attempt cannot be started again.</CardDescription></CardHeader><CardContent className="space-y-5">{quiz.questions.map((item, index) => <div key={item.id} className="rounded-xl border p-4"><div className="flex justify-between gap-3"><div className="font-medium">{index + 1}. {item.prompt}</div><div className="text-xs text-muted-foreground">{item.points} marks</div></div>{item.question_type === "multiple_choice" && <div className="mt-3 space-y-2">{(item.choices ?? []).map((choice) => <label key={choice} className="flex items-center gap-2 rounded-lg border p-3 text-sm"><input type="radio" name={item.id} checked={answers[item.id] === choice} onChange={() => setAnswers((v) => ({ ...v, [item.id]: choice }))} />{choice}</label>)}</div>}{item.question_type === "true_false" && <div className="mt-3 flex gap-2">{["True", "False"].map((choice) => <Button key={choice} type="button" variant={answers[item.id] === choice ? "default" : "outline"} onClick={() => setAnswers((v) => ({ ...v, [item.id]: choice }))}>{choice}</Button>)}</div>}{item.question_type === "short_answer" && <Input className="mt-3" value={String(answers[item.id] ?? "")} onChange={(e) => setAnswers((v) => ({ ...v, [item.id]: e.target.value }))} />}{item.question_type === "long_answer" && <textarea className="mt-3 min-h-32 w-full rounded-md border bg-transparent p-3 text-sm" value={String(answers[item.id] ?? "")} onChange={(e) => setAnswers((v) => ({ ...v, [item.id]: e.target.value }))} />}</div>)}<div className="flex justify-end"><Button disabled={saving} onClick={() => void submitStudentQuiz()}><Send className="mr-2 h-4 w-4" />Submit quiz</Button></div></CardContent></Card>}
    </>}

    {!isStudent && canManage && <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
      <Card><CardHeader><CardTitle>Assessments</CardTitle><CardDescription>Select a quiz, test or exam to manage its online questions and marking.</CardDescription></CardHeader><CardContent className="space-y-2">{assessments.length === 0 ? <div className="text-sm text-muted-foreground">No quiz-capable assessments have been created.</div> : assessments.map((item) => <Button key={item.id} className="h-auto w-full justify-start whitespace-normal py-3 text-left" variant={selectedId === item.id ? "default" : "outline"} onClick={() => void openStaffAssessment(item.id)}>{item.title}</Button>)}</CardContent></Card>

      <div className="space-y-6">
        {!selectedId ? <Card><CardContent className="p-10 text-center text-sm text-muted-foreground">Select an assessment to begin.</CardContent></Card> : <>
          <Card><CardHeader><CardTitle>{quiz?.assessment.title ?? "Assessment"} question bank</CardTitle><CardDescription>{quiz?.questions.length ?? 0} online questions attached.</CardDescription></CardHeader><CardContent className="space-y-3">{quiz?.questions.map((item, index) => <div key={item.id} className="rounded-lg border p-3"><div className="font-medium">{index + 1}. {item.prompt}</div><div className="mt-1 text-xs text-muted-foreground">{item.question_type} · {item.points} marks{item.topic_key ? ` · ${item.topic_key}` : ""}</div></div>)}</CardContent></Card>

          <Card><CardHeader><CardTitle>Add online question</CardTitle><CardDescription>Objective questions are auto-marked. Long answers are routed to the teacher review queue.</CardDescription></CardHeader><CardContent className="grid gap-4 md:grid-cols-2"><div className="grid gap-1.5 md:col-span-2"><Label>Question</Label><textarea className="min-h-24 rounded-md border bg-transparent p-3 text-sm" value={question.prompt} onChange={(e) => setQuestion((v) => ({ ...v, prompt: e.target.value }))} /></div><div className="grid gap-1.5"><Label>Type</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={question.question_type} onChange={(e) => setQuestion((v) => ({ ...v, question_type: e.target.value as QuestionType, correct_answer: "", choices: "" }))}><option value="multiple_choice">Multiple choice</option><option value="true_false">True / false</option><option value="short_answer">Short answer</option><option value="long_answer">Long answer</option></select></div><div className="grid gap-1.5"><Label>Marks</Label><Input type="number" min={0.5} step={0.5} value={question.points} onChange={(e) => setQuestion((v) => ({ ...v, points: Number(e.target.value) }))} /></div><div className="grid gap-1.5"><Label>Topic key</Label><Input value={question.topic_key} onChange={(e) => setQuestion((v) => ({ ...v, topic_key: e.target.value }))} placeholder="fractions.addition" /></div>{question.question_type === "multiple_choice" && <div className="grid gap-1.5 md:col-span-2"><Label>Choices — one per line</Label><textarea className="min-h-24 rounded-md border bg-transparent p-3 text-sm" value={question.choices} onChange={(e) => setQuestion((v) => ({ ...v, choices: e.target.value }))} /></div>}{question.question_type !== "long_answer" && <div className="grid gap-1.5 md:col-span-2"><Label>Correct answer</Label>{question.question_type === "true_false" ? <select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={question.correct_answer} onChange={(e) => setQuestion((v) => ({ ...v, correct_answer: e.target.value }))}><option value="">Select answer</option><option value="True">True</option><option value="False">False</option></select> : <Input value={question.correct_answer} onChange={(e) => setQuestion((v) => ({ ...v, correct_answer: e.target.value }))} />}</div>}<div className="md:col-span-2"><Button disabled={saving || !question.prompt.trim() || (question.question_type !== "long_answer" && !question.correct_answer)} onClick={() => void createQuestion()}><Plus className="mr-2 h-4 w-4" />Add question</Button></div></CardContent></Card>

          <Card><CardHeader><CardTitle>Attempts & written-response marking</CardTitle><CardDescription>Teachers can only mark assessments assigned to their own teacher profile; management may review the school queue.</CardDescription></CardHeader><CardContent className="space-y-4">{reviewAttempts.length === 0 ? <div className="py-6 text-center text-sm text-muted-foreground">No learner attempts yet.</div> : reviewAttempts.map((attempt) => <div key={attempt.id} className="rounded-xl border p-4"><div className="flex flex-wrap items-center justify-between gap-2"><div><div className="font-semibold">Learner {attempt.student_id.slice(0, 8)}</div><div className="text-xs text-muted-foreground">{attempt.status}{attempt.submitted_at ? ` · ${new Date(attempt.submitted_at).toLocaleString()}` : ""}</div></div><div className="font-semibold">{attempt.score ?? 0}/{attempt.max_score ?? "—"}</div></div><div className="mt-4 space-y-3">{attempt.responses.map((response) => <div key={response.id} className="rounded-lg border p-3"><div className="text-sm font-medium">{response.prompt}</div><div className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">Answer: {typeof response.answer === "string" ? response.answer : JSON.stringify(response.answer)}</div>{response.awarded_points == null ? <div className="mt-3 flex items-end gap-2"><div className="grid gap-1.5"><Label>Mark / {response.points ?? 0}</Label><Input className="w-28" type="number" min={0} max={Number(response.points ?? 0)} value={manualMarks[response.id] ?? ""} onChange={(e) => setManualMarks((v) => ({ ...v, [response.id]: e.target.value }))} /></div><Button disabled={saving || !manualMarks[response.id]} onClick={() => void saveManualMark(response.id)}><ClipboardCheck className="mr-2 h-4 w-4" />Save</Button></div> : <div className="mt-2 text-xs font-medium">Awarded {response.awarded_points}/{response.points}</div>}</div>)}</div></div>)}</CardContent></Card>
        </>}
      </div>
    </div>}

    {!isStudent && !canManage && <Card><CardContent className="p-8 text-center text-sm text-muted-foreground">Your role does not manage online assessments.</CardContent></Card>}
  </div>
}
