"use client"

import * as React from "react"
import { ClipboardList, Loader2, Plus, Send } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Assessment, createAssessment, getAcademicOverview, getAcademicTerms, getAssessments, getCurriculum, publishAssessment } from "@/api/academic"
import { useAppData } from "@/provider/dataProvider"
import { useSchoolWorkspace } from "@/provider/school_workspace_provider"

const TYPES = ["assignment", "quiz", "test", "project", "practical", "exam", "other"]

export default function AssessmentsPage() {
  const { workspace } = useSchoolWorkspace()
  const { classes, teachers } = useAppData()
  const [items, setItems] = React.useState<Assessment[]>([])
  const [terms, setTerms] = React.useState<{id:string; name:string; academic_year_id:string}[]>([])
  const [curriculum, setCurriculum] = React.useState<{subject_id:string; subject:string|null; grade_id:string}[]>([])
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [form, setForm] = React.useState({ academic_year_id:"", term_id:"", class_id:"", subject_id:"", teacher_id:"", title:"", assessment_type:"test", description:"", assessment_date:"", max_score:"100", weight:"1", is_published:false })
  const canWrite = workspace?.is_platform_admin || ["school_admin","principal","vice_principal","teacher","class_teacher"].includes(workspace?.role ?? "")
  const canPublish = workspace?.is_platform_admin || ["school_admin","principal","vice_principal"].includes(workspace?.role ?? "")

  const refresh = React.useCallback(async () => {
    setLoading(true)
    try {
      const [overview,nextTerms,nextItems,nextCurriculum] = await Promise.all([getAcademicOverview(),getAcademicTerms(),getAssessments(),getCurriculum()])
      setItems(nextItems); setTerms(nextTerms); setCurriculum(nextCurriculum)
      const term=overview.current_term??nextTerms[0]; const classroom=classes[0]
      const subject=nextCurriculum.find((x)=>x.grade_id===classroom?.grade_id)
      setForm((v)=>({...v,academic_year_id:v.academic_year_id||term?.academic_year_id||overview.current_year?.id||"",term_id:v.term_id||term?.id||"",class_id:v.class_id||classroom?.id||"",subject_id:v.subject_id||subject?.subject_id||"",teacher_id:v.teacher_id||teachers[0]?.id||""}))
    } catch(err){setError(err instanceof Error?err.message:"Unable to load assessments")}
    finally{setLoading(false)}
  },[classes,teachers])
  React.useEffect(()=>{void refresh()},[refresh])

  const availableSubjects = curriculum.filter((x)=>x.grade_id===classes.find((c)=>c.id===form.class_id)?.grade_id)
  const changeClass=(classId:string)=>{const classGrade=classes.find((c)=>c.id===classId)?.grade_id;const first=curriculum.find((x)=>x.grade_id===classGrade);setForm((v)=>({...v,class_id:classId,subject_id:first?.subject_id||""}))}

  const submit=async(event:React.FormEvent)=>{event.preventDefault();setSaving(true);setError(null);try{await createAssessment({...form,teacher_id:form.teacher_id||null,description:form.description||undefined,max_score:form.max_score,weight:form.weight});setForm((v)=>({...v,title:"",description:"",assessment_date:""}));await refresh()}catch(err){setError(err instanceof Error?err.message:"Unable to create assessment")}finally{setSaving(false)}}

  if(loading)return <div className="flex min-h-[50vh] items-center justify-center gap-3 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin"/>Loading assessments…</div>

  return <div className="space-y-6">
    <div className="rounded-2xl border bg-card p-6"><div className="flex items-center gap-2 text-sm text-muted-foreground"><ClipboardList className="h-4 w-4"/>Academic assessment</div><h1 className="mt-2 text-3xl font-bold">Assessments & Exams</h1><p className="mt-2 text-sm text-muted-foreground">Create class assessments, capture marks and publish verified results inside this school.</p></div>
    {error&&<div className="rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</div>}
    {canWrite&&<Card><CardHeader><CardTitle>Create assessment</CardTitle><CardDescription>The selected subject must be in this school's curriculum for the class grade.</CardDescription></CardHeader><CardContent><form onSubmit={submit} className="grid gap-4 md:grid-cols-4"><div className="grid gap-1.5"><Label>Term</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={form.term_id} onChange={(e)=>{const t=terms.find((x)=>x.id===e.target.value);setForm((v)=>({...v,term_id:e.target.value,academic_year_id:t?.academic_year_id??v.academic_year_id}))}}>{terms.map((t)=><option key={t.id} value={t.id}>{t.name}</option>)}</select></div><div className="grid gap-1.5"><Label>Class</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={form.class_id} onChange={(e)=>changeClass(e.target.value)}>{classes.map((c)=><option key={c.id} value={c.id}>{c.name}</option>)}</select></div><div className="grid gap-1.5"><Label>Subject</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={form.subject_id} onChange={(e)=>setForm((v)=>({...v,subject_id:e.target.value}))}>{availableSubjects.map((s)=><option key={s.subject_id} value={s.subject_id}>{s.subject}</option>)}</select></div><div className="grid gap-1.5"><Label>Teacher</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={form.teacher_id} onChange={(e)=>setForm((v)=>({...v,teacher_id:e.target.value}))}><option value="">Unassigned</option>{teachers.map((t)=><option key={t.id} value={t.id}>{t.user.username}</option>)}</select></div><div className="grid gap-1.5 md:col-span-2"><Label>Title</Label><Input value={form.title} onChange={(e)=>setForm((v)=>({...v,title:e.target.value}))} required/></div><div className="grid gap-1.5"><Label>Type</Label><select className="h-9 rounded-md border bg-transparent px-3 text-sm" value={form.assessment_type} onChange={(e)=>setForm((v)=>({...v,assessment_type:e.target.value}))}>{TYPES.map((type)=><option key={type}>{type}</option>)}</select></div><div className="grid gap-1.5"><Label>Date</Label><Input type="date" value={form.assessment_date} onChange={(e)=>setForm((v)=>({...v,assessment_date:e.target.value}))} required/></div><div className="grid gap-1.5"><Label>Maximum score</Label><Input type="number" min="0.01" step="0.01" value={form.max_score} onChange={(e)=>setForm((v)=>({...v,max_score:e.target.value}))}/></div><div className="grid gap-1.5"><Label>Weight</Label><Input type="number" min="0.01" step="0.01" value={form.weight} onChange={(e)=>setForm((v)=>({...v,weight:e.target.value}))}/></div><div className="flex items-end md:col-span-2"><Button type="submit" disabled={saving||!form.term_id||!form.class_id||!form.subject_id||!form.title}><Plus className="mr-2 h-4 w-4"/>Create assessment</Button></div></form></CardContent></Card>}
    <div className="grid gap-4 lg:grid-cols-2">{items.map((item)=><Card key={item.id}><CardHeader><div className="flex items-start justify-between gap-3"><div><CardTitle>{item.title}</CardTitle><CardDescription>{item.assessment_type} · {item.assessment_date} · max {item.max_score}</CardDescription></div><span className="rounded-full border px-2 py-1 text-xs">{item.is_published?"Published":item.is_locked?"Locked":"Draft"}</span></div></CardHeader><CardContent className="flex items-center justify-between"><p className="text-sm text-muted-foreground">Weight {item.weight}</p>{canPublish&&!item.is_published&&<Button size="sm" variant="outline" onClick={async()=>{await publishAssessment(item.id,true);await refresh()}}><Send className="mr-2 h-4 w-4"/>Publish & lock</Button>}</CardContent></Card>)}</div>
    {items.length===0&&<Card><CardContent className="py-10 text-center text-sm text-muted-foreground">No assessments have been created yet.</CardContent></Card>}
  </div>
}
