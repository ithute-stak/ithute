#!/bin/sh
set -eu

PAGE='apps/frontend/app/webmail/mail-client.tsx'
ENTRY_WRAPPER='apps/frontend/app/webmail/webmail-entry.tsx'
SHELL='apps/frontend/app/webmail/webmail-shell.tsx'
LOADING='apps/frontend/app/webmail/mail-loading.tsx'
COMPOSE='apps/frontend/app/webmail/mail-compose.tsx'
ROUTE_COMPOSE='apps/frontend/app/webmail/compose/page.tsx'
SETTINGS='apps/frontend/app/webmail/settings/page.tsx'
TYPES='apps/frontend/app/webmail/mail-types.ts'
BASE_CSS='apps/frontend/app/webmail/webmail.module.css'
SKIN='apps/frontend/app/webmail/source-skin.css'
ENTRY='apps/frontend/app/webmail/page.tsx'
LAYOUT='apps/frontend/app/webmail/layout.tsx'
POLISH='apps/backend/app/services/webmail_polish.py'
API_ROUTE='apps/backend/app/api/v1/webmail.py'

for file in "$PAGE" "$ENTRY_WRAPPER" "$SHELL" "$LOADING" "$COMPOSE" "$ROUTE_COMPOSE" "$SETTINGS" "$TYPES" "$BASE_CSS" "$SKIN" "$ENTRY" "$LAYOUT" "$POLISH" "$API_ROUTE"; do
  test -s "$file"
done

# Functional contract: keep the live production client and composer implementation.
# The public /webmail page uses the branded loading shell, which must resolve to
# the real auth/product wrapper and then the existing MailClient after mailbox authentication.
grep -F 'WebmailShell' "$ENTRY" >/dev/null
grep -F 'WebmailEntry' "$SHELL" >/dev/null
grep -F 'MailLoading' "$SHELL" >/dev/null
grep -F 'Opening iMail' "$SHELL" >/dev/null
grep -F 'Preparing your secure Ithute mailbox' "$SHELL" >/dev/null
grep -F 'MailClient' "$ENTRY_WRAPPER" >/dev/null
grep -F 'webmail("/session"' "$ENTRY_WRAPPER" >/dev/null
grep -F '/auth/login' "$ENTRY_WRAPPER" >/dev/null
grep -F 'Mailbox Login' "$ENTRY_WRAPPER" >/dev/null
grep -F 'System Login' "$ENTRY_WRAPPER" >/dev/null
! grep -F 'SourceMailClient' "$ENTRY" >/dev/null
! grep -F 'SourceMailClient' "$SHELL" >/dev/null
! grep -F 'SourceMailClient' "$ENTRY_WRAPPER" >/dev/null
grep -F 'source-skin.css' "$LAYOUT" >/dev/null
grep -F 'sourceGmailSkin' "$LAYOUT" >/dev/null

# Modern Gmail reference geometry and visual tokens from the September 2026 screenshot.
grep -Fi '#f6f8fc' "$SKIN" >/dev/null
grep -Fi '#eaf1fb' "$SKIN" >/dev/null
grep -Fi '#c2e7ff' "$SKIN" >/dev/null
grep -Fi '#d3e3fd' "$SKIN" >/dev/null
grep -F 'height: 64px' "$SKIN" >/dev/null
grep -F 'max-width: 720px' "$SKIN" >/dev/null
grep -F 'border-radius: 24px' "$SKIN" >/dev/null
grep -F 'width: 256px' "$SKIN" >/dev/null
grep -F 'width: 72px' "$SKIN" >/dev/null
grep -F 'border-radius: 16px' "$SKIN" >/dev/null
grep -F 'grid-template-columns: minmax(150px,220px) minmax(0,1fr) auto' "$SKIN" >/dev/null
grep -F 'bottom-right floating compose window' "$SKIN" >/dev/null
grep -F 'background: #f2f6fc' "$SKIN" >/dev/null
grep -F '@media (max-width: 1023px)' "$SKIN" >/dev/null
grep -F '@media (max-width: 640px)' "$SKIN" >/dev/null
grep -F 'prefers-reduced-motion' "$SKIN" >/dev/null

# The whole Webmail app must share one healthy visual language, including auth/settings/direct compose.
grep -F 'Polished sign-in surface' "$SKIN" >/dev/null
grep -F 'width: min(980px, 100%)' "$SKIN" >/dev/null
grep -F 'min-height: 540px' "$SKIN" >/dev/null
grep -F 'background: #f0f4f9' "$SKIN" >/dev/null
grep -F 'Settings page polish' "$SKIN" >/dev/null
grep -F 'Direct /webmail/compose route polish' "$SKIN" >/dev/null
grep -F '.sourceGmailSkin > div.h-screen main' "$SKIN" >/dev/null
grep -F '.sourceGmailSkin > main.min-h-screen' "$SKIN" >/dev/null

# Settings must be user-facing, branded and visual rather than exposing signature HTML.
grep -F 'Visual signature' "$SETTINGS" >/dev/null
grep -F 'contentEditable' "$SETTINGS" >/dev/null
grep -F 'Add logo / signature image' "$SETTINGS" >/dev/null
grep -F 'accept="image/png,image/jpeg,image/webp,image/gif"' "$SETTINGS" >/dev/null
grep -F 'Smart contacts' "$SETTINGS" >/dev/null
grep -F 'Contacts are learned automatically' "$SETTINGS" >/dev/null
grep -F 'wm("/folder-counts"' "$SETTINGS" >/dev/null
! grep -F '<textarea' "$SETTINGS" >/dev/null

# Signature images are sanitized and converted to embedded CID mail parts; contacts learn from correspondence.
grep -F 'SIGNATURE_ALLOWED_TAGS' "$POLISH" >/dev/null
grep -F 'sanitize_signature_html' "$POLISH" >/dev/null
grep -F 'IMAGE_DATA_RE' "$POLISH" >/dev/null
grep -F 'html_part.add_related' "$POLISH" >/dev/null
grep -F 'learn_contacts_from_headers' "$POLISH" >/dev/null
grep -F '_scan_contact_folder' "$POLISH" >/dev/null
grep -F '"incoming"' "$POLISH" >/dev/null
grep -F '"outgoing"' "$POLISH" >/dev/null

# Rich mail must keep its visual signature even when it carries files or belongs to a reply thread.
grep -F 'attachments: list[WebmailAttachment]' "$API_ROUTE" >/dev/null
grep -F 'in_reply_to: str = Field' "$API_ROUTE" >/dev/null
grep -F 'references: str = Field' "$API_ROUTE" >/dev/null
grep -F '[item.model_dump() for item in payload.attachments]' "$API_ROUTE" >/dev/null
grep -F 'attachments: list[dict] | None = None' "$POLISH" >/dev/null
grep -F 'msg.add_attachment' "$POLISH" >/dev/null
grep -F 'msg["In-Reply-To"]' "$POLISH" >/dev/null
grep -F 'msg["References"]' "$POLISH" >/dev/null
grep -F 'signature_images' "$POLISH" >/dev/null
! grep -F 'targetPath = "/send"' "$TYPES" >/dev/null

# The floating composer must support Outlook/Word-style formatting and true multi-recipient To/Cc/Bcc entry.
grep -F 'RecipientField' "$COMPOSE" >/dev/null
grep -F 'uniqueRecipients' "$COMPOSE" >/dev/null
grep -F 'Add one or more Cc recipients' "$COMPOSE" >/dev/null
grep -F 'Add one or more Bcc recipients' "$COMPOSE" >/dev/null
grep -F 'mail-word-ribbon' "$COMPOSE" >/dev/null
grep -F '>Home<' "$COMPOSE" >/dev/null
grep -F 'exec("fontName"' "$COMPOSE" >/dev/null
grep -F 'exec("fontSize"' "$COMPOSE" >/dev/null
grep -F 'insertOrderedList' "$COMPOSE" >/dev/null
grep -F 'justifyCenter' "$COMPOSE" >/dev/null
grep -F 'Increase indent' "$COMPOSE" >/dev/null
grep -F 'Formatting ribbon' "$COMPOSE" >/dev/null
grep -F '/contacts?q=' "$COMPOSE" >/dev/null

# Existing production mail UX and transport-facing functionality must stay present.
grep -F 'Search mail' "$PAGE" >/dev/null
grep -F 'Compose' "$PAGE" >/dev/null
grep -F 'Starred' "$PAGE" >/dev/null
grep -F 'history.pushState' "$PAGE" >/dev/null
grep -F 'draftStorageKey' "$PAGE" >/dev/null
grep -F 'sendMessage' "$PAGE" >/dev/null
grep -F 'webmail("/send-rich"' "$PAGE" >/dev/null
grep -F 'contentEditable' "$COMPOSE" >/dev/null
grep -F 'Cc Bcc' "$COMPOSE" >/dev/null
grep -F 'Attach files' "$COMPOSE" >/dev/null
grep -F 'onSaveDraft' "$COMPOSE" >/dev/null
grep -F 'wm("/send-rich"' "$ROUTE_COMPOSE" >/dev/null
grep -F 'wm("/identity"' "$SETTINGS" >/dev/null
grep -F 'wm("/signature"' "$SETTINGS" >/dev/null
grep -F 'wm("/contacts"' "$SETTINGS" >/dev/null

echo 'Modern Webmail UI, branded iMail loading shell, unified login entry, visual signatures, smart contacts, multi-recipient entry, Word-style composer, and rich attachment/thread signature guardrails passed.'
