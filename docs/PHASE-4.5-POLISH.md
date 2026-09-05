# Phase 4.5 — Product, UX & Operations Polish

This pass turns the Phase 1–4 control plane into a coherent administration product before DNSSEC and secondary-DNS work begins.

## Added

- Shared semantic admin design system: surfaces, buttons, forms, status pills, skeletons, empty states, toasts and typed confirmation dialogs.
- Improved navigation with active sections, breadcrumbs, quick-create actions, operations, help and onboarding entry points.
- Live command-centre metrics sourced from organizations, domains, audit events and readiness checks.
- Guided first-run onboarding for organization → domain → ownership verification → platform DNS → zone provisioning.
- Searchable audit/activity centre with tenant context, action filters and metadata inspection.
- Infrastructure status centre with readiness, session and dependency visibility.
- Contextual DNS help covering ownership, delegation, TTL, MX, SRV and CAA concepts.
- DNS editor polish: record-type guidance, TTL help, CNAME conflict hints, protected SOA/NS rows, typed destructive confirmation, copyable nameservers, JSON/CSV export, JSON import preview and change preview.
- Security centre polish: MFA setup, password change, session inventory, single-session revoke and sign-out-everywhere confirmation.
- API key console with scopes, expiry, one-time secret display and revocation.
- Organization portfolio with role/status summaries and remembered tenant context.
- Settings centre that separates safe UI preferences from server-managed secrets.
- Responsive admin surfaces, mobile table fallbacks, keyboard focus treatment and reduced-motion handling.
- Product metadata, private robots policy, favicon branding, not-found and global recovery screens.
- Semantic color tokens to keep a future selectable dark theme inexpensive.
- User-facing terminology no longer exposes development-phase labels in the primary operational screens.

## Safety and product rules

- Raw infrastructure secrets are never surfaced in general settings.
- API key secrets are one-time display only.
- DNS destructive actions require typed confirmation where appropriate.
- SOA and NS record sets are protected from generic deletion in the DNS editor.
- DNS imports are previewed before application and skip protected SOA/NS rows.
- Mail-only functionality remains clearly separated until its data plane is implemented.

## Still validated by the Phase 4 acceptance gate

Polish does not replace infrastructure acceptance. Phase 4 still requires a real authenticated zone provision, UDP and TCP authoritative queries, restart persistence, backend tests and a clean frontend/production build before Phase 5 starts.
