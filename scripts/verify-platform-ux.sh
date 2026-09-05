#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

fail() {
  echo "Platform UX verification FAILED: $*" >&2
  exit 1
}

need_file() {
  [ -f "$1" ] || fail "missing $1"
}

need_text() {
  file="$1"
  text="$2"
  grep -Fq "$text" "$file" || fail "$file is missing required marker: $text"
}

echo "== Platform UX: shared foundations =="
need_file apps/frontend/components/toast-provider.tsx
need_file apps/frontend/components/command-palette.tsx
need_file apps/frontend/components/navigation-memory.tsx
need_file apps/frontend/components/background-refresh.tsx
need_file apps/frontend/components/stable-popover.tsx
need_file apps/frontend/lib/platform-api.ts
need_file apps/frontend/app/loading.tsx
need_file apps/frontend/app/error.tsx
need_file apps/frontend/app/platform-ux.css
need_file apps/frontend/app/control-polish.css

need_text apps/frontend/app/layout.tsx "<ToastProvider>"
need_text apps/frontend/app/layout.tsx "<CommandPalette />"
need_text apps/frontend/app/layout.tsx "<NavigationMemory />"
need_text apps/frontend/app/layout.tsx "<BackgroundRefresh />"
need_text apps/frontend/app/layout.tsx 'import "./control-polish.css"'
need_text apps/frontend/components/command-palette.tsx "ctrlKey"
need_text apps/frontend/lib/platform-api.ts "const inflight = new Map"
need_text apps/frontend/lib/platform-api.ts "invalidateApiCache"
need_text apps/frontend/components/background-refresh.tsx "visibilityState"
need_text apps/frontend/components/background-refresh.tsx "ithute:notifications-updated"

echo "== Platform UX: stable dropdowns =="
need_text apps/frontend/components/stable-popover.tsx 'document.addEventListener("pointerdown"'
need_text apps/frontend/components/stable-popover.tsx 'event.key !== "Escape"'
need_text apps/frontend/components/stable-popover.tsx 'rootRef.current?.contains(target)'
need_text apps/frontend/components/control-shell.tsx "useStablePopover"
need_text apps/frontend/components/control-shell.tsx 'aria-haspopup="menu"'
need_text apps/frontend/components/control-shell.tsx "ithute-dropdown-panel"
need_text apps/frontend/app/control-polish.css ".ithute-dropdown-panel"
need_text apps/frontend/app/control-polish.css ".ithute-dropdown-item"

echo "== Platform UX: control shell =="
need_text apps/frontend/components/control-shell.tsx "ithute:sidebar:collapsed"
need_text apps/frontend/components/control-shell.tsx 'key: "k", ctrlKey: true'
need_text apps/frontend/components/control-shell.tsx "ithute:notifications-updated"
need_text apps/frontend/components/control-shell.tsx 'title="Mailbox DNS"'
need_text apps/frontend/components/control-shell.tsx "control-shell-content"
need_text apps/frontend/components/ui-kit.tsx "page-header-premium"
need_text apps/frontend/components/ui-kit.tsx "metric-card-premium"

echo "== Platform UX: accessibility and motion =="
need_text apps/frontend/app/globals.css "focus-visible"
need_text apps/frontend/app/globals.css "prefers-reduced-motion"
need_text apps/frontend/app/platform-ux.css "prefers-reduced-motion"
need_text apps/frontend/app/control-polish.css "prefers-reduced-motion"
need_text apps/frontend/components/form-enhancer.tsx "aria-label"
need_text apps/frontend/components/form-enhancer.tsx "aria-invalid"

echo "== Platform UX: notification feedback =="
need_text apps/frontend/app/notifications/page.tsx "useToast"
need_text apps/frontend/app/notifications/page.tsx "apiMutation"
need_text apps/frontend/app/notifications/page.tsx "ithute:notifications-updated"

echo "Platform UX verification PASSED"
