import api from "@/lib/axios-setup"

export type QuizAttempt = {
  id: string
  student_id: string
  status: "in_progress" | "submitted" | "needs_review" | "graded"
  started_at: string
  submitted_at?: string | null
  score?: number | string | null
  max_score?: number | string | null
}

export type AvailableQuiz = {
  id: string
  title: string
  assessment_type: string
  assessment_date: string
  max_score: number | string
  question_count: number
  attempt?: QuizAttempt | null
}

export type QuizQuestion = {
  id: string
  topic_key?: string | null
  prompt: string
  question_type: "multiple_choice" | "true_false" | "short_answer" | "long_answer"
  choices?: string[] | null
  points: number | string
}

export type QuizDefinition = {
  assessment: {
    id: string
    title: string
    assessment_type: string
    max_score: number | string
  }
  questions: QuizQuestion[]
}

export type QuizReviewResponse = {
  id: string
  question_id: string
  prompt: string
  question_type: string
  points?: number | string | null
  answer: unknown
  is_correct?: string | null
  awarded_points?: number | string | null
}

export type QuizReviewAttempt = QuizAttempt & {
  responses: QuizReviewResponse[]
}

export type QuizQuestionInput = {
  topic_key?: string | null
  prompt: string
  question_type: QuizQuestion["question_type"]
  choices?: string[] | null
  correct_answer?: unknown
  points: number
  explanation?: string | null
}

export async function getAvailableQuizzes() {
  return (await api.get<AvailableQuiz[]>("/api/quiz/available", { withCredentials: true })).data
}

export async function getQuiz(assessmentId: string) {
  return (await api.get<QuizDefinition>(`/api/quiz/assessments/${assessmentId}`, { withCredentials: true })).data
}

export async function addQuizQuestion(assessmentId: string, payload: QuizQuestionInput) {
  return (await api.post(`/api/quiz/assessments/${assessmentId}/questions`, payload, { withCredentials: true })).data
}

export async function getQuizAttempts(assessmentId: string) {
  return (await api.get<QuizReviewAttempt[]>(`/api/quiz/assessments/${assessmentId}/attempts`, { withCredentials: true })).data
}

export async function startQuizAttempt(assessmentId: string) {
  return (await api.post<QuizAttempt>(`/api/quiz/assessments/${assessmentId}/attempts`, {}, { withCredentials: true })).data
}

export async function submitQuizAttempt(attemptId: string, responses: Record<string, unknown>) {
  return (await api.post<QuizAttempt>(`/api/quiz/attempts/${attemptId}/submit`, { responses }, { withCredentials: true })).data
}

export async function markQuizResponse(responseId: string, awardedPoints: number) {
  return (await api.put(`/api/quiz/responses/${responseId}/mark`, { awarded_points: awardedPoints }, { withCredentials: true })).data
}
