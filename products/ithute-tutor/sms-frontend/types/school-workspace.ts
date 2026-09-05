export type SchoolProfile = {
  id: string
  name: string
  slug?: string | null
  school_code?: string | null
  registration_number?: string | null
  category: string
  is_registered: boolean
  is_active: boolean
  certificate_number?: string | null
  logo_url?: string | null
  motto?: string | null
  primary_color?: string | null
  secondary_color?: string | null
  accent_color?: string | null
  address?: string | null
  phone?: string | null
  email?: string | null
  website?: string | null
  timezone: string
  currency: string
  locale: string
  settings_json: Record<string, unknown>
}

export type SchoolMembership = {
  id?: string | null
  school_id: string
  role: string
  title?: string | null
  is_default: boolean
  school: SchoolProfile
}

export type SchoolWorkspace = {
  school: SchoolProfile
  role: string
  is_platform_admin: boolean
  capabilities: string[]
}
