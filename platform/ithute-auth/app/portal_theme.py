from __future__ import annotations

from . import portal


ITHUTE_AUTH_STYLE = portal._STYLE + r"""
:root{
  --brand:#1475d1;
  --brand-dark:#062f68;
  --brand-bright:#1268f3;
  --brand-soft:#edf5ff;
  --ithute-green:#249716;
  --ithute-green-bright:#56bf28;
  --ithute-green-soft:#eefbea;
  --ink:#0c2858;
  --ink-soft:#264870;
  --muted:#67809f;
  --line:#d6e3f2;
  --line-strong:#bfd2e8;
  --canvas:#f5f9fe;
  --soft:#f4f8fd;
  --soft-blue:#edf5ff;
  --shadow:0 20px 55px rgba(6,47,104,.10);
}

body{background:linear-gradient(180deg,#f9fcff 0%,#f1f7fd 100%)}
a{color:var(--brand-bright)}
button,.button{background:linear-gradient(135deg,var(--brand-bright),var(--brand));box-shadow:0 10px 22px rgba(20,117,209,.18)}
button:hover,.button:hover{background:linear-gradient(135deg,#0d5fe8,var(--brand-dark));box-shadow:0 12px 25px rgba(6,47,104,.20)}
input:focus,select:focus{border-color:var(--brand);box-shadow:0 0 0 3px rgba(20,117,209,.13)}

.auth-logo{display:inline-flex;align-items:center;gap:12px;color:var(--brand-dark);text-decoration:none}
.auth-logo:hover{text-decoration:none}
.auth-logo-mark{width:48px;height:54px;flex:0 0 auto;filter:drop-shadow(0 8px 12px rgba(6,47,104,.12))}
.auth-logo.compact .auth-logo-mark{width:36px;height:41px}
.auth-logo-copy{display:flex;flex-direction:column;line-height:1.05}
.auth-logo-title{font-size:25px;font-weight:900;letter-spacing:-.045em;color:var(--brand-dark)}
.auth-logo.compact .auth-logo-title{font-size:19px}
.auth-logo-subtitle{margin-top:5px;font-size:10px;color:#7187a2;font-weight:650;letter-spacing:.01em}
.auth-logo.compact .auth-logo-subtitle{display:none}

.auth-login-page{min-height:100vh;position:relative;overflow:hidden;background:
  radial-gradient(circle at 102% 12%,rgba(20,117,209,.10) 0 11%,transparent 11.2%),
  radial-gradient(circle at 104% 44%,transparent 0 12%,rgba(36,151,22,.10) 12.2% 16%,transparent 16.2%),
  linear-gradient(180deg,#fbfdff 0%,#f2f8fd 100%)}
.auth-login-page:before{content:"";position:absolute;inset:0;background:linear-gradient(120deg,rgba(255,255,255,.8),rgba(255,255,255,0) 45%);pointer-events:none}
.auth-mountains{position:absolute;left:0;bottom:-6px;width:min(42vw,610px);height:auto;opacity:.68;pointer-events:none}
.auth-login-inner{position:relative;z-index:2;min-height:100vh;display:flex;flex-direction:column;padding:26px 42px 20px}
.auth-login-top{display:flex;align-items:center;justify-content:space-between;gap:20px;max-width:1460px;width:100%;margin:0 auto}
.auth-back{display:inline-flex;align-items:center;gap:8px;font-size:13px;font-weight:800;color:var(--brand);padding:9px 12px;border-radius:10px}
.auth-back:hover{background:rgba(20,117,209,.07);text-decoration:none}
.auth-stage{flex:1;width:min(1430px,100%);margin:20px auto 12px;display:grid;grid-template-columns:205px minmax(390px,430px) minmax(520px,650px);gap:18px;align-items:center;justify-content:center}
.auth-promise{align-self:center;padding:16px 0 28px}
.auth-promise h2{font-size:34px;line-height:1.05;letter-spacing:-.055em;color:var(--brand-dark)}
.auth-promise h2 span{display:block;color:var(--ithute-green)}
.auth-promise-line{width:44px;height:4px;border-radius:99px;background:var(--ithute-green);margin:18px 0}
.auth-promise p{max-width:175px;font-size:16px;line-height:1.45;color:#7690aa}
.auth-card{background:rgba(255,255,255,.95);border:1px solid rgba(190,211,233,.85);border-radius:18px;box-shadow:var(--shadow);backdrop-filter:blur(14px)}
.auth-login-card{padding:31px 34px;align-self:stretch;display:flex;flex-direction:column;justify-content:center}
.auth-card-logo{margin-bottom:24px}
.auth-login-card h1{font-size:31px;color:var(--brand-dark);letter-spacing:-.05em}
.auth-login-card>p{font-size:14px;line-height:1.55;color:#6d86a4;margin-top:8px}
.auth-login-card form{margin-top:20px;gap:10px}
.auth-login-card label{font-size:12px;color:var(--brand-dark);font-weight:850}
.auth-login-card input{height:44px;border-radius:9px;background:#fbfdff;border-color:#bfd3e8;padding:10px 12px;color:#16385f}
.auth-login-card input[name="identifier"],.auth-login-card input[type="password"]{background:#eef5ff}
.auth-login-card button{height:45px;border-radius:8px;margin-top:2px;font-weight:850}
.auth-login-links{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:13px;padding-bottom:16px;border-bottom:1px solid var(--line)}
.auth-login-links a{font-size:13px;font-weight:750}
.auth-mfa-hint{margin-top:10px;padding:10px 12px;border:1px solid #d2e4f8;border-radius:9px;background:linear-gradient(135deg,#f0f7ff,#f7fbff);font-size:11px;line-height:1.48;color:#526e8d}
.auth-mfa-hint strong{color:var(--brand-dark)}
.auth-product-note{font-size:11px;line-height:1.55;color:#7188a2;margin-top:14px}

.auth-help-card{align-self:stretch;padding:27px 28px;background:linear-gradient(180deg,rgba(255,255,255,.97),rgba(248,252,255,.95));display:flex;flex-direction:column;justify-content:center}
.auth-kicker{font-size:11px;text-transform:uppercase;letter-spacing:.13em;font-weight:900;color:var(--brand-bright)}
.auth-help-card>h2{font-size:29px;color:var(--brand-dark);letter-spacing:-.055em;margin-top:7px}
.auth-help-lead{font-size:13px;line-height:1.5;color:#6d86a4;max-width:570px}
.auth-process{display:grid;gap:13px;margin-top:19px}
.auth-process-row{display:grid;grid-template-columns:34px 44px 1fr;gap:10px;align-items:center}
.auth-step{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;background:#eaf4ff;border:1px solid #c8def7;color:var(--brand-bright);font-size:13px;font-weight:900}
.auth-process-icon{width:42px;height:42px;border-radius:50%;display:grid;place-items:center;background:#f0f6fd;color:var(--brand-bright)}
.auth-process-icon svg{width:21px;height:21px}
.auth-process-copy strong{display:block;color:var(--brand-dark);font-size:13px}
.auth-process-copy p{margin:3px 0 0;font-size:12px;line-height:1.42;color:#69809b}
.auth-help-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:17px}
.auth-info-box{border:1px solid #dbe7f3;background:#fff;border-radius:12px;padding:14px 15px}
.auth-info-icon{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;background:var(--ithute-green-soft);color:var(--ithute-green);margin-bottom:9px}
.auth-info-icon.blue{background:var(--brand-soft);color:var(--brand-bright)}
.auth-info-icon svg{width:19px;height:19px}
.auth-info-box h3{font-size:13px;color:var(--brand-dark);line-height:1.3}
.auth-info-box p,.auth-info-box li{font-size:11px;line-height:1.48;color:#6d839c}
.auth-info-box p{margin-top:7px}
.auth-info-box ol{margin:8px 0 0;padding-left:19px}
.auth-info-box li+li{margin-top:4px}
.auth-secure-strip{margin-top:12px;border-radius:12px;background:linear-gradient(90deg,#eefbea 0%,#f7fff4 100%);border:1px solid #d9f0d3;padding:12px 14px;display:grid;grid-template-columns:42px 1fr auto;gap:11px;align-items:center}
.auth-secure-strip .lock{width:40px;height:40px;border-radius:10px;display:grid;place-items:center;background:#dff5d8;color:var(--ithute-green)}
.auth-secure-strip strong{font-size:12px;color:var(--brand-dark)}
.auth-secure-strip p{margin-top:2px;font-size:10px;line-height:1.4}
.auth-secure-strip .safer{padding-left:14px;border-left:1px solid #cbe9c3;color:var(--ithute-green);font-weight:850;font-size:11px;text-align:center}
.auth-login-footer{display:flex;align-items:center;justify-content:center;gap:12px;color:#8195aa;font-size:10px;min-height:28px}
.auth-login-footer span+span:before{content:"|";margin-right:12px;color:#bcc9d5}

.topbar .auth-logo{min-width:max-content}
.topbar{background:linear-gradient(180deg,var(--canvas) 76%,rgba(245,249,254,0))}
.brand{display:none}

@media(max-width:1220px){
  .auth-stage{grid-template-columns:minmax(380px,430px) minmax(500px,620px);max-width:1070px}
  .auth-promise{display:none}
}
@media(max-width:930px){
  .auth-login-inner{padding:20px}
  .auth-stage{grid-template-columns:1fr;max-width:650px;margin-top:24px;align-items:stretch}
  .auth-login-card,.auth-help-card{align-self:auto}
  .auth-help-grid{grid-template-columns:1fr 1fr}
  .auth-mountains{width:65vw;opacity:.38}
}
@media(max-width:620px){
  .auth-login-inner{padding:14px}
  .auth-login-top .auth-back{font-size:0;padding:9px}
  .auth-login-top .auth-back:after{content:"Ithute";font-size:12px}
  .auth-logo-title{font-size:21px}.auth-logo-subtitle{font-size:9px}
  .auth-logo-mark{width:40px;height:46px}
  .auth-stage{margin-top:14px;gap:12px}
  .auth-login-card,.auth-help-card{padding:22px 18px;border-radius:14px}
  .auth-login-card h1{font-size:27px}
  .auth-help-card>h2{font-size:24px}
  .auth-process-row{grid-template-columns:28px 1fr}.auth-process-icon{display:none}
  .auth-help-grid{grid-template-columns:1fr}
  .auth-secure-strip{grid-template-columns:38px 1fr}.auth-secure-strip .safer{display:none}
  .auth-login-footer{flex-wrap:wrap;gap:5px 10px}.auth-login-footer span+span:before{display:none}
}
"""


def _lock_svg() -> str:
    return """<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/><path d="M12 14v2"/></svg>"""


def _user_svg() -> str:
    return """<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="3"/><path d="M5.5 19a6.5 6.5 0 0 1 13 0"/></svg>"""


def _phone_svg() -> str:
    return """<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/></svg>"""


def _check_svg() -> str:
    return """<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="m8 12 2.5 2.5L16.5 9"/></svg>"""


def _gear_svg() -> str:
    return """<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19 13.5v-3l-2-.6a7 7 0 0 0-.7-1.7l1-1.8-2.1-2.1-1.8 1A7 7 0 0 0 11.5 5l-.6-2h-3l-.6 2a7 7 0 0 0-1.7.7l-1.8-1-2.1 2.1 1 1.8A7 7 0 0 0 2 10.5l-2 .6v3l2 .6a7 7 0 0 0 .7 1.7l-1 1.8 2.1 2.1 1.8-1a7 7 0 0 0 1.7.7l.6 2h3l.6-2a7 7 0 0 0 1.7-.7l1.8 1 2.1-2.1-1-1.8a7 7 0 0 0 .7-1.7z" transform="translate(2 -1) scale(.85)"/></svg>"""


def _auth_logo(*, compact: bool = False) -> str:
    klass = "auth-logo compact" if compact else "auth-logo"
    return f"""<a class="{klass}" href="https://ithute.co.ls" aria-label="Ithute Auth"><svg class="auth-logo-mark" viewBox="0 0 64 72" role="img" aria-label="Ithute Auth shield and lock"><defs><linearGradient id="authBlue" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1475d1"/><stop offset="1" stop-color="#062f68"/></linearGradient><linearGradient id="authGreen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7bd315"/><stop offset="1" stop-color="#249716"/></linearGradient></defs><path d="M32 2c11 0 20 9 20 20v5h5v17c0 13-10 22-25 27C17 66 7 57 7 44V27h5v-5C12 11 21 2 32 2Z" fill="url(#authBlue)"/><path d="M32 71c15-5 25-14 25-27V27H32v44Z" fill="url(#authGreen)" opacity=".97"/><path d="M20 27v-5c0-7 5-12 12-12s12 5 12 12v5" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round"/><rect x="18" y="25" width="28" height="26" rx="7" fill="#fff"/><circle cx="32" cy="36" r="4" fill="#1475d1"/><path d="M32 40v5" stroke="#1475d1" stroke-width="4" stroke-linecap="round"/></svg><span class="auth-logo-copy"><span class="auth-logo-title">Ithute Auth</span><span class="auth-logo-subtitle">Secure Access. A Brighter Tomorrow.</span></span></a>"""


def _mountains() -> str:
    return """<svg class="auth-mountains" viewBox="0 0 720 270" aria-hidden="true"><defs><linearGradient id="mountainBlue" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8fc0e8" stop-opacity=".62"/><stop offset="1" stop-color="#1475d1" stop-opacity=".14"/></linearGradient><linearGradient id="mountainGreen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8ed46e" stop-opacity=".48"/><stop offset="1" stop-color="#249716" stop-opacity=".12"/></linearGradient></defs><path d="M0 216 80 165l35 20 67-71 42 31 68-84 65 71 38-29 60 62 44-37 90 88v54H0Z" fill="url(#mountainBlue)"/><path d="M0 235 87 199l56 22 56-49 61 38 63-46 62 42 61-22 66 38 85-19 123 42v25H0Z" fill="url(#mountainGreen)"/></svg>"""


def _themed_page(title: str, body: str, *, user=None) -> str:
    nav = ""
    if user is not None:
        admin = '<a class="nav-link" href="/admin">Admin</a>' if user.is_platform_admin else ""
        nav = (
            '<div class="nav">'
            '<a class="nav-link" href="/account">Account</a>'
            '<a class="nav-link" href="/account/passkeys">Passkeys</a>'
            f"{admin}"
            '<form method="post" action="/account/logout" style="display:inline">'
            '<button class="secondary" type="submit">Sign out</button>'
            '</form></div>'
        )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{portal._e(title)} · Ithute Auth</title><style>{ITHUTE_AUTH_STYLE}</style></head>'
        '<body><div class="shell"><div class="topbar">'
        f'{_auth_logo(compact=True)}{nav}</div>{body}</div></body></html>'
    )


def _themed_login_page(*, csrf_token: str, error: str | None = None, notice: str | None = None) -> str:
    error_html = f'<div class="notice error">{portal._e(error)}</div>' if error else ""
    notice_html = f'<div class="notice">{portal._e(notice)}</div>' if notice else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign in · Ithute Auth</title><style>{ITHUTE_AUTH_STYLE}</style></head><body class="auth-login-page">{_mountains()}<div class="auth-login-inner"><header class="auth-login-top">{_auth_logo()}<a class="auth-back" href="https://ithute.co.ls" aria-label="Back to Ithute">← <span>Back to Ithute</span></a></header><main class="auth-stage"><aside class="auth-promise"><h2>One identity <span>for a brighter Lesotho</span></h2><div class="auth-promise-line"></div><p>Secure. Simple. Built for what comes next.</p></aside><section class="auth-card auth-login-card"><div class="auth-card-logo">{_auth_logo()}</div><h1>Sign in to your account</h1><p>Use one central Ithute identity to access the Ithute products and services assigned to you.</p>{notice_html}{error_html}<form method="post" action="/account/login"><input type="hidden" name="csrf_token" value="{portal._e(csrf_token)}"><label>Email or phone</label><input name="identifier" autocomplete="username" placeholder="you@ithute.co.ls" required><label>Password</label><input type="password" name="password" autocomplete="current-password" required><label>Authenticator or recovery code <span class="small">(only if MFA is enabled)</span></label><input name="mfa_code" autocomplete="one-time-code" placeholder="6-digit authenticator code or recovery code"><div class="auth-mfa-hint"><strong>New to MFA?</strong> Leave the code field empty and sign in normally. After signing in, open <strong>Account → Multi-factor authentication</strong> to enable it.</div><button type="submit">Sign in securely →</button></form><div class="auth-login-links"><a href="/forgot-password">Forgot password?</a><a href="/account/passkey-login">Use a passkey</a></div><div class="auth-product-note">Ithute Auth verifies who you are. Each Ithute product keeps its own business roles and permissions, so signing in here does not automatically grant access to every product.</div></section><section class="auth-card auth-help-card"><div class="auth-kicker">How Ithute Auth works</div><h2>One identity. Total control.</h2><p class="auth-help-lead">Your Ithute account is your central identity. Mail, LoanHub and future Ithute products can trust Ithute Auth without receiving or storing your central password.</p><div class="auth-process"><div class="auth-process-row"><div class="auth-step">1</div><div class="auth-process-icon">{_user_svg()}</div><div class="auth-process-copy"><strong>Enter your email or phone and password</strong><p>Ithute Auth checks your central account, password, account status and login security controls.</p></div></div><div class="auth-process-row"><div class="auth-step">2</div><div class="auth-process-icon">{_phone_svg()}</div><div class="auth-process-copy"><strong>Complete MFA only when it is enabled</strong><p>If your account has multi-factor authentication enabled, enter the current code from your authenticator app or one unused recovery code.</p></div></div><div class="auth-process-row"><div class="auth-step">3</div><div class="auth-process-icon">{_check_svg()}</div><div class="auth-process-copy"><strong>Ithute creates your secure central session</strong><p>Connected Ithute products identify you through secure tokens, then apply their own roles and permissions.</p></div></div></div><div class="auth-help-grid"><div class="auth-info-box"><div class="auth-info-icon">{_phone_svg()}</div><h3>Where do I get the authenticator or recovery code?</h3><p><strong>Authenticator code:</strong> the changing six-digit code from the authenticator app you connected when enabling MFA. <strong>Recovery code:</strong> one of the one-time backup codes Ithute displays after MFA is enabled. Keep recovery codes safe and offline.</p></div><div class="auth-info-box"><div class="auth-info-icon blue">{_gear_svg()}</div><h3>How to enable MFA</h3><ol><li>Sign in with your email or phone and password.</li><li>Open <strong>Account</strong> and find <strong>Multi-factor authentication</strong>.</li><li>Choose <strong>Set up authenticator</strong>.</li><li>Add the setup secret to a TOTP authenticator app.</li><li>Enter its six-digit code and choose <strong>Enable MFA</strong>.</li><li>Save the recovery codes Ithute shows you.</li></ol></div></div><div class="auth-secure-strip"><div class="lock">{_lock_svg()}</div><div><strong>Stronger security for a brighter tomorrow</strong><p>Multi-factor authentication helps protect your Ithute identity and the services connected to it.</p></div><div class="safer">Safer<br>Together</div></div></section></main><footer class="auth-login-footer"><span>© 2026 Ithute Digital Solutions</span><span>Secure central identity</span><span>Built for Lesotho</span></footer></div></body></html>"""


def apply_portal_theme() -> None:
    portal._STYLE = ITHUTE_AUTH_STYLE
    portal._page = _themed_page
    portal._login_page = _themed_login_page
