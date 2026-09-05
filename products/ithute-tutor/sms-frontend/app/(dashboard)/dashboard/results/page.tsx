"use client"

import * as React from "react"
import { FileText, Loader2, Save } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Assessment, getAcademicTerms, getAssessments, getReportCard, ReportCard, upsertAssessmentResult } from "@/api/academic"
import { useAppData } from "@/provider/dataProvider"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"

export default function ResultsPage() {
  const { workspace } = useSchoolWorkspace()
  const { students } = useAppData()
  const [assessments, setAssessments] = React.useState<Assessment[]>([])
  const [terms, setTerms] = React.useState<{id:string;name:string}[]>([])
  const [assessmentId, setAssessmentId] = React.useState("")
  const [termId, setTermId] = React.useState("")
  const [studentId, setStudentId] = React.useState("")
  const [scores, setScores] = React.useState<Record<string,string>>({})
  const [reportCard, setReportCard] = React.useState<ReportCard | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [savingId, setSavingId] = React.useState<string | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const canWrite = workspace?.is_platform_admin || ["school_admin","principal","vice_principal","teacher","class_teacher"].includes(workspace?.role ?? "")

  React.useEffect(()=>{
    void Promise.all([getAssessments(),getAcademicTerms()]).then(([nextAssessments,nextTerms])=>{setAssessments(nextAssessments);setTerms(nextTerms);setAssessmentId(nextAssessments[0]?.id??"");setTermId(nextTerms.find((t)=>t.is_current)?.id??nextTerms[0]?.id??"");setStudentId(students[0]?.id??"")}).catch((err)=>setError(err instanceof Error?err.message:"Unable to load results")).finally(()=>setLoading(false))
  },[students])

  const selected=assessments.find((item)=>item.id===assessmentId)
  const classStudents=selected?students.filter((student)=>student.class_id===selected.class_id):[]

  const saveScore=async(student:string)=>{
    if(!selected)return
    const raw=scores[student]
    if(raw==null||raw==="")return
    setSavingId(student);setError(null)
    try{await upsertAssessmentResult(selected.id,{student_id:student,score:Number(raw)})}
    catch(err){setError(err instanceof Error?err.message:"Unable to save mark")}
    finally{setSavingId(null)}
  }

  const generate=async()=>{
    if(!studentId||!termId)return
    setError(null)
    try{setReportCard(await getReportCard(studentId,termId))}
    catch(err){setError(err instanceof Error?err.message:"Unable to generate report card")}
  }

  if(loading)return <div className="flex min-h-[50vh] items-center justify-center gap-3 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin"/>Loading results…</div>

  return <div className="space-y-6">
    <div className="rounded-2xl border bg-card p-6"><div className="flex items-center gap-2 text-sm text-muted-foreground"><FileText className="h-4 w-4"/>Academic results</div><h1 className="mt-2 text-3xl font-bold">Marks & Report Cards</h1><p className="mt-2 text-sm text-muted-foreground">Capture marks before publication and generate term report cards from published school assessments.</p></div>
    {error&&<div className="rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</div>}

    {canWrite&&<Card><CardHeader><CardTitle>Capture assessment marks</CardTitle><CardDescription>Scores are validated against the assessment maximum. Locked assessments cannot be changed.</CardDescription></CardHeader><CardContent className="space-y-4"><div className="grid max-w-2xl gap-1.5"><Label>Assessment</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={assessmentId} onChange={(e)=>setAssessmentId(e.target.value)}>{assessments.map((item)=><option key={item.id} value={item.id}>{item.title} · {item.assessment_date}{item.is_locked?" · locked":""}</option>)}</select></div>{selected&&<div className="space-y-2">{classStudents.map((student)=><div key={student.id} className="grid items-center gap-3 rounded-lg border p-3 sm:grid-cols-[1fr_160px_auto]"><div><p className="font-medium">{student.user.username}</p><p className="text-xs text-muted-foreground">{student.admission_number}</p></div><Input type="number" min="0" max={selected.max_score} step="0.01" placeholder={`0 – ${selected.max_score}`} value={scores[student.id]??""} onChange={(e)=>setScores((v)=>({...v,[student.id]:e.target.value}))} disabled={selected.is_locked}/><Button size="sm" onClick={()=>void saveScore(student.id)} disabled={selected.is_locked||savingId===student.id||!scores[student.id]}>{savingId===student.id?<Loader2 className="h-4 w-4 animate-spin"/>:<Save className="h-4 w-4"/>}</Button></div>)}{classStudents.length===0&&<p className="text-sm text-muted-foreground">No current learners found in this assessment class.</p>}</div>}</CardContent></Card>}

    <Card><CardHeader><CardTitle>Generate term report card</CardTitle><CardDescription>Only assessments published by school leadership are included.</CardDescription></CardHeader><CardContent className="space-y-5"><div className="grid gap-4 md:grid-cols-3"><div className="grid gap-1.5"><Label>Learner</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={studentId} onChange={(e)=>setStudentId(e.target.value)}>{students.map((student)=><option key={student.id} value={student.id}>{student.user.username} · {student.admission_number}</option>)}</select></div><div className="grid gap-1.5"><Label>Term</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={termId} onChange={(e)=>setTermId(e.target.value)}>{terms.map((term)=><option key={term.id} value={term.id}>{term.name}</option>)}</select></div><div className="flex items-end"><Button onClick={()=>void generate()} disabled={!studentId||!termId}>Generate report card</Button></div></div>{reportCard&&<div className="rounded-xl border p-5"><div className="flex flex-col gap-1 border-b pb-4 sm:flex-row sm:items-end sm:justify-between"><div><p className="text-sm text-muted-foreground">{workspace?.school.name}</p><h2 className="text-xl font-semibold">{reportCard.student??"Learner"} · {reportCard.term}</h2></div><p className="text-2xl font-bold">{reportCard.overall_percentage==null?"—":`${reportCard.overall_percentage}%`}</p></div><div className="mt-4 space-y-2">{reportCard.subjects.map((subject)=><div key={subject.subject_id} className="flex items-center justify-between rounded-lg bg-muted/40 px-3 py-2"><div><p className="font-medium">{subject.subject}</p><p className="text-xs text-muted-foreground">{subject.assessments_count} published assessment{subject.assessments_count===1?"":"s"}</p></div><span className="font-semibold">{subject.percentage==null?"—":`${subject.percentage}%`}</span></div>)}</div></div>}</CardContent></Card>
  </div>
}
