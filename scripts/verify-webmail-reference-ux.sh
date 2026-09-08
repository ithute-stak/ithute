#!/bin/sh
set -eu

PAGE='apps/frontend/app/webmail/mail-client.tsx'
ENTRY_WRAPPER='apps/frontend/app/webmail/webmail-entry.tsx'
SHELL='apps/frontend/app/webmail/webmail-shell.tsx'
LOADING='apps/frontend/app/webmail/mail-loading.tsx'
COMPOSE='apps/frontend/app/webmail/mail-compose.tsx'
ROUTE_COMPOSE='apps/frontend/app/webmail/compose/page.tsx'
SETTINGS='apps/frontend/app/webmail/settings/page.tsx'
EXTERNAL='apps/frontend/app/webmail/external/page.tsx'
TYPES='apps/frontend/app/webmail/mail-types.ts'
BASE_CSS='apps/frontend/app/webmail/webmail.module.css'
SKIN='apps/frontend/app/webmail/source-skin.css'
APPROVED_CSS='apps/frontend/app/webmail/approved-webmail.css'
SETTINGS_CSS='apps/frontend/app/webmail/approved-settings.css'
LINK_CONTENT='apps/frontend/app/webmail/mail-content.tsx'
LINK_ENHANCER='apps/frontend/app/webmail/mail-link-enhancer.tsx'
ROUTE_FRAME='apps/frontend/app/webmail/webmail-route-frame.tsx'
MOBILE_ACTIONS='apps/frontend/app/webmail/webmail-mobile-actions.tsx'
NEXT_MOBILE_CSS='apps/frontend/app/webmail/next-generation-mobile-nav.css'
EXTERNAL_SHORTCUT='apps/frontend/app/webmail/webmail-external-shortcut.tsx'
ENTRY='apps/frontend/app/webmail/page.tsx'
LAYOUT='apps/frontend/app/webmail/layout.tsx'
POLISH='apps/backend/app/services/webmail_polish.py'
API_ROUTE='apps/backend/app/api/v1/webmail.py'

for file in \
  "$PAGE" "$ENTRY_WRAPPER" "$SHELL" "$LOADING" "$COMPOSE" "$ROUTE_COMPOSE" \
  "$SETTINGS" "$EXTERNAL" "$TYPES" "$BASE_CSS" "$SKIN" "$APPROVED_CSS" \
  "$SETTINGS_CSS" "$LINK_CONTENT" "$LINK_ENHANCER" "$ROUTE_FRAME" \
  "$MOBILE_ACTIONS" "$NEXT_MOBILE_CSS" "$EXTERNAL_SHORTCUT" "$ENTRY" "$LAYOUT" "$POLISH" "$API_ROUTE"; do
  test -s "$file"
done

# Functional contract: keep the live production client, auth paths and composer.
grep -F 'WebmailShell' "$ENTRY" >/dev/null
grep -F 'WebmailEntry' "$SHELL" >/dev/null
grep -F 'MailLoading' "$SHELL" >/dev/null
grep -F 'Opening iMail' "$SHELL" >/dev/null
grep -F 'Preparing your secure Ithute mailbox' "$SHELL" >/dev/null
grep -F 'MailClient' "$ENTRY_WRAPPER" >/dev/null
grep -F 'webmail("/session"' "$ENTRY_WRAPPER" >/dev/null
grep -F '/auth/login' "$ENTRY_WRAPPER" >/dev/null
grep -F 'systemMfaRequired' "$ENTRY_WRAPPER" >/dev/null
grep -F 'System account' "$ENTRY_WRAPPER" >/dev/null
grep -F 'Other email account' "$ENTRY_WRAPPER" >/dev/null
! grep -F 'SourceMailClient' "$ENTRY" >/dev/null
! grep -F 'SourceMailClient' "$SHELL" >/dev/null
! grep -F 'SourceMailClient' "$ENTRY_WRAPPER" >/dev/null

# The approved Ithute presentation layer must be loaded last and route-aware.
grep -F 'source-skin.css' "$LAYOUT" >/dev/null
grep -F 'approved-webmail.css' "$LAYOUT" >/dev/null
grep -F 'approved-settings.css' "$LAYOUT" >/dev/null
grep -F 'MailLinkEnhancer' "$LAYOUT" >/dev/null
grep -F 'WebmailMobileActions' "$LAYOUT" >/dev/null
grep -F 'WebmailRouteFrame' "$LAYOUT" >/dev/null
grep -F 'sourceGmailSkin' "$LAYOUT" >/dev/null
grep -F 'imail-approved-ui' "$ROUTE_FRAME" >/dev/null
grep -F 'imail-route-external' "$ROUTE_FRAME" >/dev/null
grep -F 'imail-route-settings' "$ROUTE_FRAME" >/dev/null

# Approved sign-in: branded two-panel desktop, dedicated mobile presentation.
grep -F 'imail-login-page' "$ENTRY_WRAPPER" >/dev/null
grep -F 'Your business inbox' "$ENTRY_WRAPPER" >/dev/null
grep -F 'done right.' "$ENTRY_WRAPPER" >/dev/null
grep -F 'Professional email' "$ENTRY_WRAPPER" >/dev/null
grep -F 'Secure & private' "$ENTRY_WRAPPER" >/dev/null
grep -F 'Work anywhere' "$ENTRY_WRAPPER" >/dev/null
grep -F 'Built for teams' "$ENTRY_WRAPPER" >/dev/null
grep -F '.imail-login-shell' "$APPROVED_CSS" >/dev/null
grep -F 'grid-template-columns: minmax(0, 1.18fr)' "$APPROVED_CSS" >/dev/null
grep -F '.imail-login-mobile-brand' "$APPROVED_CSS" >/dev/null
grep -F '@media (max-width: 639.98px)' "$APPROVED_CSS" >/dev/null
grep -F 'min-height: 100dvh' "$APPROVED_CSS" >/dev/null
grep -F 'env(safe-area-inset-bottom)' "$APPROVED_CSS" >/dev/null

# Hosted and external message readers must detect URLs without executing remote HTML.
grep -F 'imail-detected-link' "$LINK_ENHANCER" >/dev/null
grep -F 'noopener noreferrer nofollow' "$LINK_ENHANCER" >/dev/null
grep -F 'target = "_blank"' "$LINK_ENHANCER" >/dev/null
grep -F '.imail-route-webmail article .whitespace-pre-wrap' "$LINK_ENHANCER" >/dev/null
grep -F 'MailContent' "$EXTERNAL" >/dev/null
grep -F 'MailPrivacyNote' "$EXTERNAL" >/dev/null
grep -F 'linkifyText' "$LINK_CONTENT" >/dev/null
grep -F 'noopener noreferrer nofollow' "$LINK_CONTENT" >/dev/null
grep -F 'text-[#0869d7]' "$LINK_CONTENT" >/dev/null
grep -F '.imail-detected-link' "$APPROVED_CSS" >/dev/null

# Current mobile inbox contract: purpose-built phone actions stay available on
# the mailbox list and disappear while a message reader is open.
grep -F 'imail-mobile-primary-compose' "$MOBILE_ACTIONS" >/dev/null
grep -F 'imail-mobile-home-actions' "$MOBILE_ACTIONS" >/dev/null
grep -F 'imail-mobile-profile' "$MOBILE_ACTIONS" >/dev/null
grep -F 'imail-mobile-search-filter' "$MOBILE_ACTIONS" >/dev/null
grep -F 'imail-mobile-nav' "$MOBILE_ACTIONS" >/dev/null
grep -F '<span>Inbox</span>' "$MOBILE_ACTIONS" >/dev/null
grep -F '<span>Starred</span>' "$MOBILE_ACTIONS" >/dev/null
grep -F '<span>Drafts</span>' "$MOBILE_ACTIONS" >/dev/null
grep -F '<span>Sent</span>' "$MOBILE_ACTIONS" >/dev/null
grep -F '<span>Attachments</span>' "$MOBILE_ACTIONS" >/dev/null
grep -F '<span>More</span>' "$MOBILE_ACTIONS" >/dev/null
grep -F 'article.imail-message-reader' "$MOBILE_ACTIONS" >/dev/null
grep -F 'messageOpen' "$MOBILE_ACTIONS" >/dev/null
grep -F 'min-height: 100dvh' "$NEXT_MOBILE_CSS" >/dev/null
grep -F 'env(safe-area-inset-bottom)' "$NEXT_MOBILE_CSS" >/dev/null
grep -F '.imail-mobile-primary-compose' "$NEXT_MOBILE_CSS" >/dev/null
grep -F '.imail-mobile-home-actions' "$NEXT_MOBILE_CSS" >/dev/null
grep -F '.imail-mobile-profile' "$NEXT_MOBILE_CSS" >/dev/null
grep -F '.imail-mobile-search-filter' "$NEXT_MOBILE_CSS" >/dev/null
grep -F '.imail-mobile-nav' "$NEXT_MOBILE_CSS" >/dev/null

# The guest login owns its external-account CTA; the compact shortcut appears
# only after the authenticated Webmail shell exists.
grep -F 'WebmailExternalShortcut' "$ENTRY" >/dev/null
grep -F 'mailboxReady' "$EXTERNAL_SHORTCUT" >/dev/null
grep -F 'Other email account' "$EXTERNAL_SHORTCUT" >/dev/null

# Settings should match the dark Ithute Green approved presentation on desktop
# and collapse to one touch-friendly column on narrow devices.
grep -F '.imail-route-settings main.min-h-screen' "$SETTINGS_CSS" >/dev/null
grep -F '#081512' "$SETTINGS_CSS" >/dev/null
grep -F '@media (max-width: 1023.98px)' "$SETTINGS_CSS" >/dev/null
grep -F '@media (max-width: 639.98px)' "$SETTINGS_CSS" >/dev/null

# Keep the original Gmail-reference geometry underneath as a compatibility
# baseline for the existing MailClient structure and composer behavior.
grep -Fi '#f6f8fc' "$SKIN" >/dev/null
grep -Fi '#eaf1fb' "$SKIN" >/dev/null
grep -F 'bottom-right floating compose window' "$SKIN" >/dev/null
grep -F 'prefers-reduced-motion' "$SKIN" >/dev/null

# Settings remain user-facing and visual rather than exposing signature HTML.
grep -F 'Visual signature' "$SETTINGS" >/dev/null
grep -F 'contentEditable' "$SETTINGS" >/dev/null
grep -F 'Add logo / signature image' "$SETTINGS" >/dev/null
grep -F 'accept="image/png,image/jpeg,image/webp,image/gif"' "$SETTINGS" >/dev/null
grep -F 'Smart contacts' "$SETTINGS" >/dev/null
grep -F 'Contacts are learned automatically' "$SETTINGS" >/dev/null
grep -F 'wm("/folder-counts"' "$SETTINGS" >/dev/null
! grep -F '<textarea' "$SETTINGS" >/dev/null

# Signature images are sanitized and converted to embedded CID mail parts;
# contacts continue to learn from correspondence.
grep -F 'SIGNATURE_ALLOWED_TAGS' "$POLISH" >/dev/null
grep -F 'sanitize_signature_html' "$POLISH" >/dev/null
grep -F 'IMAGE_DATA_RE' "$POLISH" >/dev/null
grep -F 'html_part.add_related' "$POLISH" >/dev/null
grep -F 'learn_contacts_from_headers' "$POLISH" >/dev/null
grep -F '_scan_contact_folder' "$POLISH" >/dev/null
grep -F '"incoming"' "$POLISH" >/dev/null
grep -F '"outgoing"' "$POLISH" >/dev/null

# Rich mail keeps files, reply threading and visual signatures.
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

# Existing production mail UX and transport-facing functionality stays present.
grep -F 'Search mail' "$PAGE" >/dev/null
grep -F 'Compose' "$PAGE" >/dev/null
grep -F 'Starred' "$PAGE" >/dev/null
grep -F 'history.pushState' "$PAGE" >/dev/null
grep -F 'draftStorageKey' "$PAGE" >/dev/null
grep -F 'sendMessage' "$PAGE" >/dev/null
grep -F 'webmail("/send-rich"' "$PAGE" >/dev/null
grep -F 'RecipientField' "$COMPOSE" >/dev/null
grep -F 'mail-word-ribbon' "$COMPOSE" >/dev/null
grep -F 'contentEditable' "$COMPOSE" >/dev/null
grep -F 'Cc Bcc' "$COMPOSE" >/dev/null
grep -F 'Attach files' "$COMPOSE" >/dev/null
grep -F 'onSaveDraft' "$COMPOSE" >/dev/null
grep -F 'wm("/send-rich"' "$ROUTE_COMPOSE" >/dev/null
grep -F 'wm("/identity"' "$SETTINGS" >/dev/null
grep -F 'wm("/signature"' "$SETTINGS" >/dev/null
grep -F 'wm("/contacts"' "$SETTINGS" >/dev/null

echo 'Approved responsive Ithute Mail UI, mobile navigation, safe clickable links, dark settings, rich compose and mail transport guardrails passed.'
