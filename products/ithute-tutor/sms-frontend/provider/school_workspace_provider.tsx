"use client"

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react"

import {
  activateSchoolWorkspace,
  getCurrentSchoolWorkspace,
  getSchoolWorkspaces,
} from "@/api/schools/workspace"
import type { SchoolMembership, SchoolWorkspace } from "@/types/school-workspace"

type SchoolWorkspaceContextValue = {
  workspace: SchoolWorkspace | null
  memberships: SchoolMembership[]
  loading: boolean
  hasMultipleSchools: boolean
  hasSchool: boolean
  switchSchool: (schoolId: string) => Promise<void>
  refreshWorkspace: () => Promise<void>
}

const SchoolWorkspaceContext = createContext<SchoolWorkspaceContextValue | null>(null)

export function SchoolWorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [workspace, setWorkspace] = useState<SchoolWorkspace | null>(null)
  const [memberships, setMemberships] = useState<SchoolMembership[]>([])
  const [loading, setLoading] = useState(true)
  const autoActivationAttempted = useRef(false)

  const refreshWorkspace = useCallback(async () => {
    setLoading(true)
    try {
      const available = await getSchoolWorkspaces()
      setMemberships(available)

      try {
        const current = await getCurrentSchoolWorkspace()
        setWorkspace(current)
        autoActivationAttempted.current = false
        return
      } catch {
        setWorkspace(null)
      }

      // A user with exactly one school should never have to understand the
      // platform's tenant model. Enter that school automatically so Tutor
      // behaves like the school's own standalone system.
      if (available.length === 1 && !autoActivationAttempted.current) {
        autoActivationAttempted.current = true
        await activateSchoolWorkspace(available[0].school_id)
        const current = await getCurrentSchoolWorkspace()
        setWorkspace(current)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshWorkspace()
  }, [refreshWorkspace])

  useEffect(() => {
    const school = workspace?.school
    if (!school) return

    const root = document.documentElement
    if (school.primary_color) root.style.setProperty("--school-primary", school.primary_color)
    else root.style.removeProperty("--school-primary")

    if (school.secondary_color) root.style.setProperty("--school-secondary", school.secondary_color)
    else root.style.removeProperty("--school-secondary")

    if (school.accent_color) root.style.setProperty("--school-accent", school.accent_color)
    else root.style.removeProperty("--school-accent")

    document.title = `${school.name} | !thute Tutor`
  }, [workspace])

  const switchSchool = useCallback(async (schoolId: string) => {
    if (workspace?.school.id === schoolId) return
    await activateSchoolWorkspace(schoolId)
    // A hard reload deliberately clears school-specific Redux/query/component
    // state so data from the previous school can never bleed into the next UI.
    window.location.reload()
  }, [workspace?.school.id])

  const value = useMemo(
    () => ({
      workspace,
      memberships,
      loading,
      hasMultipleSchools: memberships.length > 1,
      hasSchool: memberships.length > 0,
      switchSchool,
      refreshWorkspace,
    }),
    [workspace, memberships, loading, switchSchool, refreshWorkspace],
  )

  return <SchoolWorkspaceContext.Provider value={value}>{children}</SchoolWorkspaceContext.Provider>
}

export function useSchoolWorkspace() {
  const context = useContext(SchoolWorkspaceContext)
  if (!context) {
    throw new Error("useSchoolWorkspace must be used inside SchoolWorkspaceProvider")
  }
  return context
}
