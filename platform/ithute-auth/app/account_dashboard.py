from __future__ import annotations

from . import portal


ACCOUNT_DASHBOARD_STYLE = r"""
.auth-account-dashboard{background:linear-gradient(180deg,#f7fbff 0%,#edf5fd 100%);min-height:100vh}
.auth-account-dashboard .shell{max-width:none;width:100%;padding:14px 24px 32px}
.auth-account-dashboard .topbar{max-width:none;padding:8px 2px 14px;position:sticky;top:0;z-index:30;background:rgba(247,251,255,.92);backdrop-filter:blur(16px);border-bottom:1px solid rgba(191,210,232,.65)}
.auth-account-dashboard .nav{gap:4px}
.auth-account-dashboard .nav-link{border-radius:10px;color:#264870}
.auth-account-dashboard .nav-link:hover{background:#e8f2fc;color:#062f68}
.auth-account-dashboard .topbar form button{box-shadow:none}
.auth-account-dashboard .hero{margin-top:14px;padding:26px 28px;border-radius:22px;background:linear-gradient(118deg,#062f68 0%,#0d61b0 62%,#249716 140%);box-shadow:0 18px 45px rgba(6,47,104,.16);align-items:center;position:relative;overflow:hidden}
.auth-account-dashboard .hero:after{content:"";position:absolute;width:360px;height:360px;border:62px solid rgba(255,255,255,.07);border-radius:50%;right:-150px;top:-190px;pointer-events:none}
.auth-account-dashboard .hero .eyebrow,.auth-account-dashboard .hero h1,.auth-account-dashboard .hero p{color:#fff}
.auth-account-dashboard .hero .eyebrow{opacity:.78}
.auth-account-dashboard .hero p{opacity:.80;max-width:760px}
.auth-account-dashboard .hero .badge{border-color:rgba(255,255,255,.22);background:rgba(255,255,255,.12);color:#fff}
.auth-account-dashboard .hero .id-card{position:relative;z-index:1;min-width:330px;max-width:460px;background:rgba(255,255,255,.12);border-color:rgba(255,255,255,.2);box-shadow:none;backdrop-filter:blur(10px)}
.auth-account-dashboard .hero .id-card .label,.auth-account-dashboard .hero .id-card p{color:rgba(255,255,255,.72)}
.auth-account-dashboard .hero .id-card code{display:block;background:rgba(255,255,255,.12);color:#fff;border:1px solid rgba(255,255,255,.16);padding:9px 10px}
.auth-account-dashboard .grid{gap:14px;margin-top:14px}
.auth-account-dashboard .card{border-radius:16px;border-color:#d7e4f1;box-shadow:0 8px 24px rgba(6,47,104,.055)}
.auth-account-dashboard .contact-card{min-height:132px;padding:17px 18px;background:linear-gradient(180deg,#fff,#fbfdff)}
.auth-account-dashboard .contact-card .value{font-size:15px;color:#0c2858}
.auth-account-dashboard .contact-card .contact-actions{padding-top:10px}
.auth-account-dashboard .contact-card .button{font-size:12px;padding:8px 10px}
.auth-dashboard-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:14px 0}
.auth-kpi{position:relative;overflow:hidden;background:#fff;border:1px solid #d7e4f1;border-radius:16px;padding:17px 18px;box-shadow:0 8px 24px rgba(6,47,104,.05)}
.auth-kpi:before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:#1475d1}
.auth-kpi.green:before{background:#249716}.auth-kpi.amber:before{background:#d89a16}
.auth-kpi .kpi-label{font-size:10px;font-weight:900;text-transform:uppercase;letter-spacing:.11em;color:#7086a0}
.auth-kpi .kpi-value{display:block;margin-top:8px;font-size:27px;line-height:1;font-weight:900;letter-spacing:-.045em;color:#062f68}
.auth-kpi .kpi-value.small-value{font-size:15px;line-height:1.3;letter-spacing:-.01em}
.auth-kpi .kpi-meta{margin-top:7px;font-size:11px;color:#7a8ea5}
.auth-dashboard-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:14px 0}
.auth-dashboard-toolbar .toolbar-copy strong{display:block;color:#0c2858;font-size:16px}.auth-dashboard-toolbar .toolbar-copy span{display:block;color:#7288a2;font-size:12px;margin-top:3px}
.auth-dashboard-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.auth-dashboard-actions button,.auth-dashboard-actions a{font-size:12px;padding:9px 12px;border-radius:10px}
.auth-dashboard-actions .ghost-action{background:#fff;color:#0c2858;border:1px solid #cbdced;box-shadow:none}
.auth-dashboard-actions .ghost-action:hover{background:#f2f7fd;text-decoration:none}
.auth-data-card{grid-column:span 12;padding:0;overflow:hidden}
.auth-data-head{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:18px 20px;border-bottom:1px solid #dfebf5;background:linear-gradient(180deg,#fff,#fbfdff)}
.auth-data-head h2{font-size:17px;color:#0c2858}.auth-data-head p{font-size:11px;margin-top:3px}
.auth-table-tools{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.auth-table-search{width:240px;max-width:45vw;height:36px;font-size:12px;background:#f8fbff}
.auth-table-scroll{width:100%;overflow:auto}
.auth-data-table{width:100%;border-collapse:collapse;min-width:760px}
.auth-data-table th{padding:11px 16px;background:#f5f9fe;border-bottom:1px solid #dce9f4;color:#647c98;font-size:10px;font-weight:900;letter-spacing:.09em;white-space:nowrap}
.auth-data-table td{padding:13px 16px;border-bottom:1px solid #e7eef6;color:#35516f;font-size:12px;vertical-align:middle}
.auth-data-table tbody tr:hover{background:#f8fbff}
.auth-data-table .table-primary{font-weight:850;color:#0c2858}.auth-data-table .table-secondary{font-size:10px;color:#8092a8;margin-top:3px;line-height:1.35}
.auth-data-table .row-actions{justify-content:flex-start}.auth-data-table .row-actions button{font-size:11px;padding:7px 9px;box-shadow:none}
.auth-pagination{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;background:#fbfdff;border-top:1px solid #e0eaf4;color:#7488a0;font-size:11px}
.auth-pagination-controls{display:flex;align-items:center;gap:6px}.auth-pagination-controls button{padding:7px 10px;font-size:11px;box-shadow:none}.auth-pagination-controls button:disabled{opacity:.45;cursor:not-allowed}
.auth-page-size{width:auto;height:34px;padding:5px 28px 5px 8px;font-size:11px}
.auth-modal{width:min(560px,calc(100vw - 28px));border:0;border-radius:18px;padding:0;box-shadow:0 28px 90px rgba(4,31,70,.28);overflow:hidden;color:#0c2858}
.auth-modal::backdrop{background:rgba(2,22,49,.48);backdrop-filter:blur(3px)}
.auth-modal-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:18px 20px;background:linear-gradient(115deg,#062f68,#1475d1);color:#fff}.auth-modal-head h3{color:#fff;font-size:18px}.auth-modal-head p{color:rgba(255,255,255,.75);font-size:11px;margin-top:4px}.auth-modal-close{width:32px;height:32px;border-radius:9px;background:rgba(255,255,255,.14);padding:0;box-shadow:none;font-size:18px}.auth-modal-close:hover{background:rgba(255,255,255,.22);box-shadow:none}
.auth-modal-body{padding:20px;background:#fff}.auth-modal-body .card{border:0;box-shadow:none;padding:0}.auth-modal-body .section-head{margin-bottom:13px}.auth-modal-body .section-head h2{display:none}.auth-modal-body .section-head p{font-size:12px}.auth-modal-body .grid{display:block;margin:0}.auth-modal-body .col-5,.auth-modal-body .col-7{width:100%;display:block}.auth-modal-body .callout{margin-bottom:14px}.auth-modal-body form{gap:10px}
.auth-account-dashboard .danger-zone{background:linear-gradient(180deg,#fff,#fff9f8);border-color:#f1d1cd}
.auth-account-dashboard .security-card,.auth-account-dashboard .dashboard-hidden{display:none!important}
@media(max-width:1100px){.auth-dashboard-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.auth-account-dashboard .hero{align-items:flex-start}.auth-account-dashboard .hero .id-card{min-width:280px}}
@media(max-width:760px){.auth-account-dashboard .shell{padding:10px 12px 24px}.auth-account-dashboard .topbar{position:relative;flex-direction:column;align-items:flex-start}.auth-account-dashboard .nav{width:100%;overflow:auto;flex-wrap:nowrap}.auth-account-dashboard .hero{display:block;padding:20px}.auth-account-dashboard .hero .id-card{margin-top:16px;min-width:0;max-width:none}.auth-dashboard-kpis{grid-template-columns:1fr 1fr}.auth-dashboard-toolbar{align-items:flex-start;flex-direction:column}.auth-dashboard-actions{justify-content:flex-start}.auth-table-search{width:100%;max-width:none}.auth-data-head{align-items:flex-start;flex-direction:column}.auth-table-tools{width:100%}.auth-pagination{align-items:flex-start;flex-direction:column}.auth-account-dashboard .contact-card{grid-column:span 12}}
@media(max-width:460px){.auth-dashboard-kpis{grid-template-columns:1fr}.auth-dashboard-actions>*{width:100%}.auth-dashboard-actions{width:100%}}
"""


ACCOUNT_DASHBOARD_SCRIPT = r"""
(() => {
  const byTitle = (title) => [...document.querySelectorAll('.card')].find((card) => card.querySelector('h2')?.textContent.trim() === title);
  const overview = byTitle('Security overview');
  const contact = byTitle('Contact verification') || byTitle('Confirm contact verification');
  const password = byTitle('Change password');
  const mfa = byTitle('Multi-factor authentication');
  const sessions = byTitle('Product sessions');
  const activity = byTitle('Security activity');
  const guidance = byTitle('Security guidance');
  const grid = document.querySelector('.grid');
  const hero = document.querySelector('.hero');
  if (!grid || !hero) return;

  const contactCards = [...grid.querySelectorAll('.contact-card')];
  const stats = overview ? [...overview.querySelectorAll('.stat')] : [];
  const statValue = (index, fallback = '—') => stats[index]?.querySelector('strong')?.textContent.trim() || fallback;
  const statusText = (card, fallback = '—') => card?.querySelector('.badge')?.textContent.trim() || fallback;
  const isMfaEnabled = contactCards[2]?.querySelector('.badge')?.classList.contains('good') === true;

  const kpis = document.createElement('section');
  kpis.className = 'auth-dashboard-kpis';
  const definitions = [
    ['Active product sessions', statValue(0, '0'), 'Current trusted product sessions', ''],
    ['Successful security events', statValue(1, '0'), 'Recent successful identity events', 'green'],
    ['MFA protection', statusText(contactCards[2], 'Not enabled'), 'Central account protection', isMfaEnabled ? 'green' : 'amber'],
    ['Latest activity', statValue(2), 'Most recent security event', '']
  ];
  definitions.forEach(([label, value, meta, tone]) => {
    const card = document.createElement('div');
    card.className = `auth-kpi ${tone}`;
    const small = String(value).length > 18 ? ' small-value' : '';
    card.innerHTML = `<div class="kpi-label">${label}</div><span class="kpi-value${small}">${value}</span><div class="kpi-meta">${meta}</div>`;
    kpis.appendChild(card);
  });
  hero.insertAdjacentElement('afterend', kpis);
  if (overview) overview.remove();

  const toolbar = document.createElement('section');
  toolbar.className = 'auth-dashboard-toolbar';
  toolbar.innerHTML = `<div class="toolbar-copy"><strong>Identity & security controls</strong><span>Manage your central Ithute identity without leaving this dashboard.</span></div><div class="auth-dashboard-actions"><button type="button" class="ghost-action" data-open-auth-modal="contact-modal">Contact & recovery</button><button type="button" class="ghost-action" data-open-auth-modal="password-modal">Change password</button><button type="button" data-open-auth-modal="mfa-modal">Manage MFA</button><a class="ghost-action" href="/account/passkeys">Passkeys</a></div>`;
  kpis.insertAdjacentElement('afterend', toolbar);

  const moveIntoDialog = (card, id, title, subtitle) => {
    if (!card) return;
    const dialog = document.createElement('dialog');
    dialog.className = 'auth-modal';
    dialog.id = id;
    const head = document.createElement('div');
    head.className = 'auth-modal-head';
    head.innerHTML = `<div><h3>${title}</h3><p>${subtitle}</p></div><button type="button" class="auth-modal-close" aria-label="Close">×</button>`;
    const body = document.createElement('div');
    body.className = 'auth-modal-body';
    while (card.firstChild) body.appendChild(card.firstChild);
    dialog.append(head, body);
    document.body.appendChild(dialog);
    card.remove();
    head.querySelector('.auth-modal-close').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) dialog.close();
    });
  };
  moveIntoDialog(contact, 'contact-modal', 'Contact & recovery', 'Review or verify the recovery contacts linked to this Ithute identity.');
  moveIntoDialog(password, 'password-modal', 'Change password', 'Changing your password revokes product sessions as a security precaution.');
  moveIntoDialog(mfa, 'mfa-modal', 'Multi-factor authentication', 'Add or manage authenticator-based protection for every product using this identity.');

  document.querySelectorAll('[data-open-auth-modal]').forEach((button) => {
    button.addEventListener('click', () => document.getElementById(button.dataset.openAuthModal)?.showModal());
  });

  const buildTable = (card, kind) => {
    if (!card) return;
    card.classList.add('auth-data-card');
    const head = card.querySelector('.section-head');
    const rows = [...card.querySelectorAll(':scope > .row')];
    const empty = card.querySelector(':scope > .empty');
    if (head) {
      head.className = 'auth-data-head';
      const tools = document.createElement('div');
      tools.className = 'auth-table-tools';
      tools.innerHTML = `<input class="auth-table-search" type="search" placeholder="Search ${kind === 'sessions' ? 'sessions' : 'security activity'}…" aria-label="Search"><select class="auth-page-size" aria-label="Rows per page"><option value="8">8 rows</option><option value="12">12 rows</option><option value="20">20 rows</option></select>`;
      head.appendChild(tools);
    }
    if (!rows.length) return;

    const wrap = document.createElement('div');
    wrap.className = 'auth-table-scroll';
    const table = document.createElement('table');
    table.className = 'auth-data-table';
    const thead = document.createElement('thead');
    thead.innerHTML = kind === 'sessions'
      ? '<tr><th>Product</th><th>Session details</th><th>Device</th><th>Status</th><th>Action</th></tr>'
      : '<tr><th>Security event</th><th>Details</th><th>Status</th></tr>';
    const tbody = document.createElement('tbody');
    table.append(thead, tbody);
    wrap.appendChild(table);

    rows.forEach((row) => {
      const tr = document.createElement('tr');
      tr.dataset.search = row.textContent.toLowerCase();
      const title = row.querySelector('.row-title');
      const badge = title?.querySelector('.badge') || row.querySelector('.row-actions .badge');
      if (badge?.parentNode === title) badge.remove();
      const metas = [...row.querySelectorAll('.row-meta')];
      const actions = row.querySelector('.row-actions');
      const primary = document.createElement('td');
      primary.innerHTML = `<div class="table-primary">${title?.textContent.trim() || '—'}</div>`;
      const details = document.createElement('td');
      details.innerHTML = `<div>${metas[0]?.textContent.trim() || '—'}</div>`;
      if (kind === 'sessions') {
        const device = document.createElement('td');
        device.innerHTML = `<div class="table-secondary">${metas[1]?.textContent.trim() || 'Unknown device'}</div>`;
        const status = document.createElement('td');
        if (badge) status.appendChild(badge);
        const action = document.createElement('td');
        if (actions) action.appendChild(actions);
        tr.append(primary, details, device, status, action);
      } else {
        const status = document.createElement('td');
        if (badge) status.appendChild(badge);
        tr.append(primary, details, status);
      }
      tbody.appendChild(tr);
      row.remove();
    });
    if (empty) empty.remove();
    card.appendChild(wrap);

    const pagination = document.createElement('div');
    pagination.className = 'auth-pagination';
    pagination.innerHTML = '<span class="auth-page-summary"></span><div class="auth-pagination-controls"><button type="button" class="ghost prev">Previous</button><span class="auth-page-number"></span><button type="button" class="ghost next">Next</button></div>';
    card.appendChild(pagination);

    const search = head?.querySelector('.auth-table-search');
    const size = head?.querySelector('.auth-page-size');
    const prev = pagination.querySelector('.prev');
    const next = pagination.querySelector('.next');
    const summary = pagination.querySelector('.auth-page-summary');
    const pageNumber = pagination.querySelector('.auth-page-number');
    let page = 1;
    const render = () => {
      const query = (search?.value || '').trim().toLowerCase();
      const pageSize = Number(size?.value || 8);
      const all = [...tbody.querySelectorAll('tr')];
      const filtered = all.filter((tr) => !query || tr.dataset.search.includes(query));
      const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
      page = Math.min(page, pages);
      all.forEach((tr) => tr.hidden = true);
      filtered.slice((page - 1) * pageSize, page * pageSize).forEach((tr) => tr.hidden = false);
      const start = filtered.length ? (page - 1) * pageSize + 1 : 0;
      const end = Math.min(page * pageSize, filtered.length);
      summary.textContent = `${start}–${end} of ${filtered.length}`;
      pageNumber.textContent = `Page ${page} of ${pages}`;
      prev.disabled = page <= 1;
      next.disabled = page >= pages;
    };
    search?.addEventListener('input', () => { page = 1; render(); });
    size?.addEventListener('change', () => { page = 1; render(); });
    prev.addEventListener('click', () => { page = Math.max(1, page - 1); render(); });
    next.addEventListener('click', () => { page += 1; render(); });
    render();
  };

  buildTable(sessions, 'sessions');
  buildTable(activity, 'activity');
  if (guidance) guidance.classList.add('auth-guidance-card');
})();
"""


def apply_account_dashboard() -> None:
    base_page = portal._page

    def dashboard_page(title: str, body: str, *, user=None) -> str:
        rendered = base_page(title, body, user=user)
        if title != "Account" or user is None:
            return rendered
        rendered = rendered.replace("<body>", '<body class="auth-account-dashboard">', 1)
        rendered = rendered.replace("</style>", ACCOUNT_DASHBOARD_STYLE + "</style>", 1)
        rendered = rendered.replace("</body>", f"<script>{ACCOUNT_DASHBOARD_SCRIPT}</script></body>", 1)
        return rendered

    portal._page = dashboard_page
