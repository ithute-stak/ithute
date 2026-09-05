import api from "@/lib/axios-setup"

export type TransferStatus = "released" | "under_review" | "accepted" | "rejected" | "cancelled" | "expired"

export type TransferEvent = {
  id: string
  event_type: string
  from_status?: string | null
  to_status?: string | null
  school_id?: string | null
  actor_user_id?: string | null
  note?: string | null
  metadata: Record<string, unknown>
  created_at?: string | null
}

export type SchoolTransfer = {
  id: string
  reference_number?: string | null
  student_id: string
  source_school_id: string
  source_school?: string | null
  destination_school_id?: string | null
  destination_school?: string | null
  direction: "incoming" | "outgoing" | "platform"
  status: TransferStatus
  transfer_reason?: string | null
  note?: string | null
  destination_note?: string | null
  rejection_reason?: string | null
  consent_confirmed: boolean
  records_verified: boolean
  expires_at: string
  released_at?: string | null
  claimed_at?: string | null
  accepted_at?: string | null
  rejected_at?: string | null
  cancelled_at?: string | null
  proposed_start_date?: string | null
  destination_class_id?: string | null
  review_available: boolean
  records_available: boolean
  events: TransferEvent[]
}

export type TransferIssueResult = {
  transfer_id: string
  reference_number: string
  student_id: string
  code: string
  status: TransferStatus
  expires_at: string
  message: string
}

export type TransferReviewPacket = {
  transfer: SchoolTransfer
  learner: {
    id: string
    admission_number: string
    first_name?: string | null
    last_name?: string | null
    date_of_birth?: string | null
    gender?: string | null
    nationality?: string | null
  }
  source_school: { id: string; name?: string | null }
  current_enrollment: {
    id?: string | null
    class_id?: string | null
    class?: string | null
    grade?: string | null
    academic_year?: string | null
    term?: string | null
    start_date?: string | null
  }
  attendance_summary: {
    records_reviewed: number
    present: number
    absent: number
    late: number
    excused: number
  }
  published_academic_summary: {
    assessment_date: string
    title: string
    assessment_type: string
    subject?: string | null
    score?: number | null
    max_score: number
    percentage?: number | null
    is_absent: boolean
    remarks?: string | null
  }[]
  privacy: {
    scope: string
    full_history_available_after_acceptance: boolean
    finance_shared: boolean
    source_records_mutable_by_destination: boolean
  }
}

export type LearnerTransferDossier = {
  transfer: {
    id: string
    reference_number?: string | null
    student_id: string
    source_school_id: string
    destination_school_id: string
    accepted_at?: string | null
  }
  learner: {
    id: string
    admission_number: string
    first_name?: string | null
    last_name?: string | null
    date_of_birth?: string | null
    gender?: string | null
    nationality?: string | null
  }
  shared_source_schools: { school_id: string; school?: string | null }[]
  enrollments: {
    id: string
    school_id: string
    school?: string | null
    class?: { id: string; name: string; grade_id?: string | null; grade?: string | null } | null
    academic_year_id?: string | null
    academic_year?: string | null
    term_id?: string | null
    term?: string | null
    start_date?: string | null
    end_date?: string | null
    status: string
    withdrawal_reason?: string | null
    transfer_destination?: string | null
  }[]
  attendance: {
    id: string
    school_id: string
    school?: string | null
    date: string
    status: string
    remarks?: string | null
    class?: { id: string; name: string; grade_id?: string | null; grade?: string | null } | null
    academic_year?: string | null
    term?: string | null
  }[]
  academic_history: {
    school_id: string
    school?: string | null
    academic_year?: string | null
    term?: string | null
    class?: { id: string; name: string; grade_id?: string | null; grade?: string | null } | null
    subject?: string | null
    assessment_id: string
    title: string
    assessment_type: string
    assessment_date: string
    max_score: number
    score?: number | null
    percentage?: number | null
    is_absent: boolean
    is_excused: boolean
    remarks?: string | null
  }[]
  privacy: {
    access: string
    finance_shared: boolean
    source_records_mutable_by_destination: boolean
  }
}

export async function getSchoolTransfers() {
  return (await api.get<SchoolTransfer[]>("/api/student-transfers", { withCredentials: true })).data
}

export async function releaseTransfer(studentId: string, payload: {
  transfer_reason: string
  note?: string
  consent_confirmed: boolean
  validity_days?: number
}) {
  return (await api.post<TransferIssueResult>(`/api/student-transfers/${studentId}/issue`, {
    transfer_reason: payload.transfer_reason,
    note: payload.note || null,
    consent_confirmed: payload.consent_confirmed,
    validity_days: payload.validity_days ?? 7,
  }, { withCredentials: true })).data
}

export async function claimTransfer(code: string) {
  return (await api.post<{ transfer_id: string; reference_number: string; status: TransferStatus; review_url: string }>(
    "/api/student-transfers/claim",
    { code },
    { withCredentials: true },
  )).data
}

export async function getTransferReview(transferId: string) {
  return (await api.get<TransferReviewPacket>(`/api/student-transfers/${transferId}/review`, { withCredentials: true })).data
}

export async function acceptTransfer(transferId: string, payload: {
  class_id: string
  start_date: string
  records_verified: boolean
  destination_note?: string
}) {
  return (await api.post(`/api/student-transfers/${transferId}/accept`, {
    ...payload,
    destination_note: payload.destination_note || null,
  }, { withCredentials: true })).data
}

export async function rejectTransfer(transferId: string, reason: string) {
  return (await api.post(`/api/student-transfers/${transferId}/reject`, { reason }, { withCredentials: true })).data
}

export async function cancelTransfer(transferId: string, reason: string) {
  return (await api.post(`/api/student-transfers/${transferId}/cancel`, { reason }, { withCredentials: true })).data
}

export async function getTransferRecords(transferId: string) {
  return (await api.get<LearnerTransferDossier>(`/api/student-transfers/${transferId}/records`, { withCredentials: true })).data
}
