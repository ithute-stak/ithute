from __future__ import annotations

import html

from . import oauth


def _login_html(
    fields: dict[str, str],
    *,
    identifier: str = "",
    error: str | None = None,
) -> str:
    hidden = "\n".join(
        f'<input type="hidden" name="{html.escape(key, quote=True)}" value="{html.escape(value, quote=True)}">'
        for key, value in fields.items()
    )
    identifier_value = html.escape(identifier, quote=True)
    error_html = (
        f'<div class="alert" role="alert"><span class="alert-dot">!</span><span>{html.escape(error)}</span></div>'
        if error
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>Sign in · Ithute</title>
  <style>
    :root{{--ink:#173228;--muted:#6d7f76;--green:#123a38;--green-2:#285b55;--gold:#d8c56a;--gold-soft:#fff8d9;--paper:#f4f6f4;--line:#dce5e0;--danger:#a52a37}}
    *{{box-sizing:border-box}}
    html,body{{min-height:100%}}
    body{{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--ink);background:radial-gradient(circle at 12% 10%,rgba(216,197,106,.20),transparent 28rem),radial-gradient(circle at 92% 16%,rgba(52,112,103,.16),transparent 30rem),linear-gradient(135deg,#edf3ef 0%,#f7f8f6 50%,#eef4f1 100%)}}
    .shell{{min-height:100vh;display:grid;place-items:center;padding:28px}}
    .frame{{width:min(1060px,100%);display:grid;grid-template-columns:.92fr 1.08fr;overflow:hidden;border:1px solid rgba(18,58,56,.12);border-radius:30px;background:#fff;box-shadow:0 34px 90px rgba(18,58,56,.15)}}
    .brand{{position:relative;overflow:hidden;padding:46px;background:linear-gradient(145deg,#0d302e 0%,#123a38 54%,#194b47 100%);color:#fff}}
    .brand:before{{content:"";position:absolute;width:300px;height:300px;border-radius:50%;right:-120px;top:-100px;background:rgba(216,197,106,.10)}}
    .brand:after{{content:"";position:absolute;width:260px;height:260px;border-radius:50%;left:-130px;bottom:-150px;background:rgba(74,177,158,.10)}}
    .brand-inner{{position:relative;z-index:1;display:flex;min-height:470px;flex-direction:column}}
    .logo{{display:flex;align-items:center;gap:12px;text-decoration:none;color:#fff}}
    .logo-mark{{display:grid;width:48px;height:48px;place-items:center;border-radius:15px;background:var(--gold);color:var(--green);font-size:25px;font-weight:950;box-shadow:0 14px 30px rgba(0,0,0,.18)}}
    .logo-name{{font-size:20px;font-weight:950;letter-spacing:-.04em}}
    .logo-sub{{margin-top:2px;font-size:9px;font-weight:800;letter-spacing:.18em;text-transform:uppercase;color:rgba(255,255,255,.48)}}
    .eyebrow{{margin-top:62px;font-size:10px;font-weight:900;letter-spacing:.16em;text-transform:uppercase;color:var(--gold)}}
    .brand h1{{max-width:440px;margin:14px 0 0;font-size:42px;line-height:1.02;letter-spacing:-.055em}}
    .brand p{{max-width:440px;margin:18px 0 0;font-size:14px;line-height:1.85;color:rgba(255,255,255,.67)}}
    .trust{{margin-top:auto;display:grid;gap:10px}}
    .trust-row{{display:flex;align-items:flex-start;gap:10px;font-size:11px;line-height:1.55;color:rgba(255,255,255,.72)}}
    .check{{display:grid;place-items:center;flex:0 0 auto;width:20px;height:20px;border:1px solid rgba(216,197,106,.35);border-radius:50%;background:rgba(216,197,106,.09);color:var(--gold);font-weight:900}}
    .panel{{padding:50px 56px 46px;background:#fff}}
    .secure{{display:inline-flex;align-items:center;gap:7px;padding:7px 10px;border:1px solid #dce9e3;border-radius:999px;background:#f3f8f5;color:#367062;font-size:9px;font-weight:900;letter-spacing:.1em;text-transform:uppercase}}
    .secure-dot{{width:7px;height:7px;border-radius:50%;background:#3ea37e;box-shadow:0 0 0 4px rgba(62,163,126,.10)}}
    .panel h2{{margin:20px 0 0;font-size:36px;line-height:1.05;letter-spacing:-.045em}}
    .lead{{margin:10px 0 28px;color:var(--muted);font-size:13px;line-height:1.65}}
    form{{display:grid;gap:16px}}
    label{{display:grid;gap:7px;font-size:11px;font-weight:850;color:#2a4036}}
    .hint{{font-weight:600;color:#84928b}}
    .field{{position:relative}}
    input{{width:100%;min-height:50px;padding:12px 14px;border:1px solid #d6e0db;border-radius:12px;background:#fff;color:#20372d;font:inherit;font-size:14px;font-weight:650;outline:none;transition:border .15s,box-shadow .15s,background .15s}}
    input:focus{{border-color:#4d8178;box-shadow:0 0 0 4px rgba(40,91,85,.10);background:#fcfefd}}
    input::placeholder{{color:#a4afa9}}
    .password input{{padding-right:50px}}
    .toggle{{position:absolute;right:8px;top:8px;min-height:34px;padding:0 10px;border:0;border-radius:8px;background:#eef4f1;color:#49685f;font-size:10px;font-weight:850;cursor:pointer}}
    .mfa{{padding:15px;border:1px solid #eadfaa;border-radius:14px;background:#fffdf5}}
    .mfa label{{color:#564d2d}}
    .mfa input{{border-color:#e5dba9;background:#fff}}
    .alert{{display:flex;align-items:flex-start;gap:10px;margin:0 0 2px;padding:12px 14px;border:1px solid #efc5ca;border-radius:12px;background:#fff4f5;color:#8e2633;font-size:12px;font-weight:750;line-height:1.5}}
    .alert-dot{{display:grid;place-items:center;flex:0 0 auto;width:19px;height:19px;border-radius:50%;background:#a52a37;color:white;font-size:11px;font-weight:950}}
    .submit{{min-height:50px;margin-top:2px;border:0;border-radius:12px;background:var(--green);color:white;font:inherit;font-size:13px;font-weight:900;cursor:pointer;box-shadow:0 13px 25px rgba(18,58,56,.16);transition:transform .15s,background .15s,box-shadow .15s}}
    .submit:hover{{transform:translateY(-1px);background:var(--green-2);box-shadow:0 16px 30px rgba(18,58,56,.20)}}
    .foot{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:22px;padding-top:20px;border-top:1px solid #edf1ef;color:#8a9790;font-size:10px;line-height:1.5}}
    .foot strong{{color:#587269}}
    @media(max-width:820px){{.shell{{padding:16px}}.frame{{grid-template-columns:1fr;max-width:560px;border-radius:24px}}.brand{{padding:27px 28px}}.brand-inner{{min-height:0}}.eyebrow{{margin-top:30px}}.brand h1{{font-size:30px}}.brand p{{margin-top:12px}}.trust{{display:none}}.panel{{padding:32px 28px 28px}}.panel h2{{font-size:31px}}}}
    @media(max-width:460px){{.shell{{padding:0;place-items:stretch}}.frame{{min-height:100vh;border:0;border-radius:0}}.brand{{padding:22px}}.brand p{{display:none}}.eyebrow{{margin-top:24px}}.brand h1{{font-size:27px}}.panel{{padding:28px 22px}}}}
  </style>
</head>
<body>
  <div class="shell">
    <main class="frame">
      <section class="brand" aria-label="Ithute identity">
        <div class="brand-inner">
          <div class="logo">
            <div class="logo-mark">!</div>
            <div><div class="logo-name">thute</div><div class="logo-sub">Secure identity</div></div>
          </div>
          <div class="eyebrow">One account · trusted access</div>
          <h1>Your Ithute account opens the services you work with.</h1>
          <p>Sign in once to continue securely to your organisation, hosting, domains, email and other Ithute services.</p>
          <div class="trust">
            <div class="trust-row"><span class="check">✓</span><span>PKCE-protected OAuth authorization with short-lived codes.</span></div>
            <div class="trust-row"><span class="check">✓</span><span>MFA and recovery-code verification when enabled on your account.</span></div>
            <div class="trust-row"><span class="check">✓</span><span>Your password stays with Ithute Identity and is never sent to the requesting application.</span></div>
          </div>
        </div>
      </section>
      <section class="panel">
        <span class="secure"><span class="secure-dot"></span> Protected sign-in</span>
        <h2>Welcome back</h2>
        <p class="lead">Use your central Ithute account to continue. After verification you will return automatically to the service that requested access.</p>
        {error_html}
        <form method="post" action="/oauth/authorize">
          {hidden}
          <label>Email address or phone
            <input name="identifier" value="{identifier_value}" autocomplete="username" required autofocus placeholder="name@company.co.ls">
          </label>
          <label>Password
            <div class="field password">
              <input id="oauth-password" type="password" name="password" autocomplete="current-password" required placeholder="Enter your password">
              <button class="toggle" type="button" onclick="var p=document.getElementById('oauth-password');var showing=p.type==='text';p.type=showing?'password':'text';this.textContent=showing?'Show':'Hide';">Show</button>
            </div>
          </label>
          <div class="mfa">
            <label>Authenticator or recovery code <span class="hint">Only required when MFA is enabled</span>
              <input name="mfa_code" inputmode="numeric" autocomplete="one-time-code" placeholder="6-digit code or recovery code">
            </label>
          </div>
          <button class="submit" type="submit">Continue securely →</button>
        </form>
        <div class="foot"><span>auth.ithute.co.ls</span><strong>Ithute Digital Solutions</strong></div>
      </section>
    </main>
  </div>
</body>
</html>"""


def apply_oauth_theme() -> None:
    """Apply presentation only; OAuth validation and credential handling stay in oauth.py."""

    oauth._login_html = _login_html
