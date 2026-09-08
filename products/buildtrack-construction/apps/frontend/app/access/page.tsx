"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import styles from "../security.module.css";

type Row = Record<string, unknown>;
type Assignment = { role_id: number; branch_id: number | null; site_id: number | null; is_primary: boolean };
type Catalog = { roles: Row[]; branches: Row[]; sites: Row[] };
type Me = { user: Row; permissions: string[]; session_id: number };
type Context = { user: Row; permissions: string[]; company_wide: boolean; branches: Row[]; sites: Row[] };
type Tab = "overview" | "users" | "security" | "sessions" | "events" | "profile";

function text(row: Row | null | undefined, key: string): string { return String(row?.[key] ?? ""); }
function num(row: Row | null | undefined, key: string): number { return Number(row?.[key] ?? 0); }
function arr(row: Row | null | undefined, key: string): Row[] { const value = row?.[key]; return Array.isArray(value) ? value as Row[] : []; }

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }, cache: "no-store" });
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail : JSON.stringify(payload?.detail ?? payload));
  return payload as T;
}

function roleScope(catalog: Catalog, roleId: number): string { return text(catalog.roles.find((role)=>num(role,"id")===roleId), "scope_level"); }

export default function AccessPage() {
  const router = useRouter();
  const search = useSearchParams();
  const [me, setMe] = useState<Me | null>(null);
  const [context, setContext] = useState<Context | null>(null);
  const [catalog, setCatalog] = useState<Catalog>({ roles: [], branches: [], sites: [] });
  const [users, setUsers] = useState<Row[]>([]);
  const [sessions, setSessions] = useState<Row[]>([]);
  const [events, setEvents] = useState<Row[]>([]);
  const [policy, setPolicy] = useState<Row | null>(null);
  const [active, setActive] = useState<Tab>(search.get("changePassword") === "1" ? "profile" : "overview");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [resetToken, setResetToken] = useState("");

  const permissions = useMemo(() => new Set(me?.permissions ?? []), [me]);
  const canViewUsers = permissions.has("users.view");
  const canManageUsers = permissions.has("users.manage");
  const canViewSecurity = permissions.has("security.view");
  const canManageSecurity = permissions.has("security.manage");

  const refresh = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [who, scope, ownSessions] = await Promise.all([api<Me>("/access/me"), api<Context>("/access/context"), api<Row[]>("/access/sessions")]);
      setMe(who); setContext(scope); setSessions(ownSessions);
      if (who.permissions.includes("users.view")) {
        const [userRows, accessCatalog] = await Promise.all([api<Row[]>("/access/users"), api<Catalog>("/access/assignment-catalog")]);
        setUsers(userRows); setCatalog(accessCatalog);
      }
      if (who.permissions.includes("security.view")) {
        const [securityPolicy, securityEvents] = await Promise.all([api<Row>("/access/security-policy"), api<Row[]>("/access/security-events?limit=300")]);
        setPolicy(securityPolicy); setEvents(securityEvents);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not load access controls";
      if (message.toLowerCase().includes("authentication") || message.toLowerCase().includes("session")) router.replace("/login");
      else setError(message);
    } finally { setLoading(false); }
  }, [router]);

  useEffect(() => { void refresh(); }, [refresh]);

  function done(message: string) { setNotice(message); setError(""); setResetToken(""); window.setTimeout(()=>setNotice(""),3500); void refresh(); }
  async function logout() { try { await api<void>("/access/logout", { method: "POST" }); } finally { router.replace("/login"); router.refresh(); } }

  const visibleTabs: Array<[Tab,string]> = [["overview","My access"], ...(canViewUsers ? [["users","Users"] as [Tab,string]] : []), ...(canViewSecurity ? [["security","Security policy"] as [Tab,string],["events","Security events"] as [Tab,string]] : []), ["sessions","My sessions"], ["profile","My security"]];

  if (loading && !me) return <main className={styles.screen}><div className={styles.authWrap}><section className={styles.authCard}><div className={styles.brand}><span className={styles.brandMark}>BT</span><div className={styles.brandText}><strong>BuildTrack</strong><span>Loading access context…</span></div></div></section></div></main>;

  return <main className={styles.shell}>
    <header className={styles.topbar}><div className={styles.topbarLeft}><span className={styles.brandMark}>BT</span><div><strong>Access & Security</strong><span>{text(me?.user,"full_name")} · {text(me?.user,"username")}</span></div></div><div className={styles.topActions}><Link className={styles.navLink} href="/">Operations</Link><button className={styles.logout} onClick={()=>void logout()}>Sign out</button></div></header>
    <nav className={styles.nav}>{visibleTabs.map(([id,label])=><button key={id} className={active===id?styles.active:""} onClick={()=>setActive(id)}>{label}</button>)}</nav>
    <div className={styles.content}>
      {error && <div className={`${styles.alert} ${styles.error}`}>{error}</div>}{notice && <div className={`${styles.alert} ${styles.success}`}>{notice}</div>}
      {active === "overview" && <Overview context={context} me={me} />}
      {active === "users" && canViewUsers && <UsersPanel users={users} catalog={catalog} canManage={canManageUsers} onDone={done} setError={setError} resetToken={resetToken} setResetToken={setResetToken} />}
      {active === "security" && canViewSecurity && <SecurityPanel policy={policy} canManage={canManageSecurity} onDone={done} setError={setError} />}
      {active === "sessions" && <SessionsPanel sessions={sessions} onDone={done} setError={setError} />}
      {active === "events" && canViewSecurity && <EventsPanel events={events} users={users} />}
      {active === "profile" && <ProfilePanel user={me?.user ?? {}} onDone={done} setError={setError} />}
    </div>
  </main>;
}

function Overview({ context, me }: { context: Context | null; me: Me | null }) {
  const assignments = arr(context?.user, "assignments");
  const modules = Array.from(new Set((me?.permissions ?? []).map((permission)=>permission.split(".")[0]))).sort();
  return <><section className={styles.hero}><div><span className={`${styles.badge} ${styles.badgeGreen}`}>Phase 2 · Operational</span><h1>Your controlled access context.</h1><p>BuildTrack resolves every permission through an active role assignment at company, branch or site level. Sessions are revocable and every security-sensitive event is recorded.</p></div><div className={styles.asideNote}>{context?.company_wide ? "Company-wide access" : "Scoped branch/site access"}</div></section>
    <section className={styles.stats}><div className={styles.stat}><span>Role assignments</span><strong>{assignments.length}</strong></div><div className={styles.stat}><span>Permissions</span><strong>{me?.permissions.length ?? 0}</strong></div><div className={styles.stat}><span>Branches</span><strong>{context?.company_wide ? "All" : context?.branches.length ?? 0}</strong></div><div className={styles.stat}><span>Sites</span><strong>{context?.company_wide ? "All" : context?.sites.length ?? 0}</strong></div></section>
    <section className={styles.rowGrid}><div className={styles.panel}><div className={styles.panelHead}><div><h2>Assigned roles</h2><p>Active company, branch and site responsibilities.</p></div></div>{assignments.length ? <div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Role</th><th>Scope</th><th>Location</th></tr></thead><tbody>{assignments.map((assignment)=><tr key={num(assignment,"id")}><td><strong>{text(assignment,"role_name")}</strong><div className={styles.muted}>{text(assignment,"role_code")}</div></td><td>{text(assignment,"scope_level")}</td><td>{text(assignment,"site_name") || text(assignment,"branch_name") || "Whole company"}</td></tr>)}</tbody></table></div> : <div className={styles.empty}>No active role assignments.</div>}</div>
    <div className={styles.panel}><div className={styles.panelHead}><div><h2>Available modules</h2><p>Derived from your effective permissions.</p></div></div><div className={styles.permissions}>{modules.map((module)=><span className={styles.permission} key={module}>{module.replaceAll("_"," ")}</span>)}</div></div></section></>;
}

function UsersPanel({ users, catalog, canManage, onDone, setError, resetToken, setResetToken }: { users: Row[]; catalog: Catalog; canManage: boolean; onDone:(message:string)=>void; setError:(value:string)=>void; resetToken:string; setResetToken:(value:string)=>void }) {
  const [showCreate,setShowCreate]=useState(false); const [editing,setEditing]=useState<Row|null>(null);
  const [form,setForm]=useState({username:"",email:"",full_name:"",phone:"",employee_number:"",job_title:""});
  const [assignments,setAssignments]=useState<Assignment[]>([{role_id:0,branch_id:null,site_id:null,is_primary:true}]);
  const [busy,setBusy]=useState(false);

  function addAssignment(){setAssignments([...assignments,{role_id:0,branch_id:null,site_id:null,is_primary:false}]);}
  function updateAssignment(index:number, patch:Partial<Assignment>){setAssignments(assignments.map((item,i)=>i===index?{...item,...patch}:item));}
  function removeAssignment(index:number){if(assignments.length>1)setAssignments(assignments.filter((_,i)=>i!==index).map((item,i)=>({...item,is_primary:i===0})));}
  function assignmentPayload(items:Assignment[]){return items.map((item,index)=>({role_id:item.role_id,branch_id:item.branch_id||null,site_id:item.site_id||null,is_primary:index===0}));}

  async function create(event:FormEvent){event.preventDefault();setBusy(true);setError("");try{if(assignments.some(item=>!item.role_id))throw new Error("Select a role for every assignment");const result=await api<{temporary_password?:string|null}>("/access/users",{method:"POST",body:JSON.stringify({...form,assignments:assignmentPayload(assignments)})});setForm({username:"",email:"",full_name:"",phone:"",employee_number:"",job_title:""});setAssignments([{role_id:0,branch_id:null,site_id:null,is_primary:true}]);setShowCreate(false);onDone("User created. Temporary password: "+(result.temporary_password??"provided by administrator"));}catch(err){setError(err instanceof Error?err.message:"Could not create user");}finally{setBusy(false);}}
  async function saveAssignments(){if(!editing)return;setBusy(true);setError("");try{await api(`/access/users/${num(editing,"id")}/assignments`,{method:"PUT",body:JSON.stringify({assignments:assignmentPayload(assignments)})});setEditing(null);onDone("Role assignments updated");}catch(err){setError(err instanceof Error?err.message:"Could not update assignments");}finally{setBusy(false);}}
  async function action(user:Row,kind:"unlock"|"reset"|"revoke"|"suspend"|"activate"){setError("");try{if(kind==="unlock"){await api(`/access/users/${num(user,"id")}/unlock`,{method:"POST"});onDone("Account unlocked");}else if(kind==="reset"){const result=await api<{reset_token:string}>(`/access/users/${num(user,"id")}/reset-token`,{method:"POST"});setResetToken(result.reset_token);onDone("One-time reset token issued");}else if(kind==="revoke"){await api(`/access/users/${num(user,"id")}/sessions/revoke-all`,{method:"POST"});onDone("All active sessions revoked");}else{await api(`/access/users/${num(user,"id")}`,{method:"PATCH",body:JSON.stringify({status:kind==="suspend"?"suspended":"active",is_active:true})});onDone(kind==="suspend"?"Account suspended":"Account activated");}}catch(err){setError(err instanceof Error?err.message:"Action failed");}}
  function startAssignments(user:Row){setEditing(user);const existing=arr(user,"assignments").map((item,index)=>({role_id:num(item,"role_id"),branch_id:num(item,"branch_id")||null,site_id:num(item,"site_id")||null,is_primary:index===0}));setAssignments(existing.length?existing:[{role_id:0,branch_id:null,site_id:null,is_primary:true}]);}

  return <><section className={styles.hero}><div><span className={styles.badge}>Identity administration</span><h1>Users, roles and operational scope.</h1><p>Create staff accounts and bind each role to the whole company, one branch or one site. Users may hold multiple active assignments.</p></div>{canManage&&<button className={`${styles.btn} ${styles.primary}`} onClick={()=>setShowCreate(!showCreate)}>{showCreate?"Close":"Create user"}</button>}</section>
  {showCreate&&<section className={styles.panel}><div className={styles.panelHead}><div><h2>New BuildTrack user</h2><p>A strong temporary password is generated automatically and shown once.</p></div></div><form className={styles.form} onSubmit={create}><div className={styles.grid2}><label className={styles.field}><span>Full name</span><input value={form.full_name} onChange={e=>setForm({...form,full_name:e.target.value})} required/></label><label className={styles.field}><span>Username</span><input value={form.username} onChange={e=>setForm({...form,username:e.target.value.toLowerCase()})} required/></label><label className={styles.field}><span>Email</span><input type="email" value={form.email} onChange={e=>setForm({...form,email:e.target.value})} required/></label><label className={styles.field}><span>Phone</span><input value={form.phone} onChange={e=>setForm({...form,phone:e.target.value})}/></label><label className={styles.field}><span>Employee number</span><input value={form.employee_number} onChange={e=>setForm({...form,employee_number:e.target.value})}/></label><label className={styles.field}><span>Job title</span><input value={form.job_title} onChange={e=>setForm({...form,job_title:e.target.value})}/></label></div><AssignmentEditor assignments={assignments} catalog={catalog} update={updateAssignment} remove={removeAssignment}/><div className={styles.toolbar}><button type="button" className={`${styles.btn} ${styles.secondary}`} onClick={addAssignment}>Add another role</button><button className={`${styles.btn} ${styles.primary}`} disabled={busy}>{busy?"Creating…":"Create secure account"}</button></div></form></section>}
  {resetToken&&<div className={styles.resetBox}><strong>One-time password reset token</strong><br/>{resetToken}<br/><span className={styles.muted}>Copy this now. BuildTrack stores only its hash and the token expires automatically.</span></div>}
  {editing&&<section className={styles.panel}><div className={styles.panelHead}><div><h2>Edit access · {text(editing,"full_name")}</h2><p>Replacing assignments takes effect on the user&apos;s next authorised request.</p></div></div><AssignmentEditor assignments={assignments} catalog={catalog} update={updateAssignment} remove={removeAssignment}/><div className={styles.toolbar}><button className={`${styles.btn} ${styles.secondary}`} onClick={addAssignment}>Add role</button><button className={`${styles.btn} ${styles.primary}`} onClick={()=>void saveAssignments()} disabled={busy}>Save assignments</button><button className={`${styles.btn} ${styles.secondary}`} onClick={()=>setEditing(null)}>Cancel</button></div></section>}
  <section className={styles.panel}><div className={styles.panelHead}><div><h2>User directory</h2><p>{users.length} account(s) in the single company.</p></div></div><div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>User</th><th>Status</th><th>Roles</th><th>Last login</th><th>Actions</th></tr></thead><tbody>{users.map(user=><tr key={num(user,"id")}><td><strong>{text(user,"full_name")}</strong><div className={styles.muted}>{text(user,"username")} · {text(user,"email")}</div></td><td><span className={styles.badge}>{text(user,"status")}</span>{Boolean(user.must_change_password)&&<div className={styles.muted}>Password change required</div>}</td><td>{arr(user,"assignments").map(item=><div key={num(item,"id")}><span className={styles.code}>{text(item,"role_code")}</span> <span className={styles.muted}>{text(item,"site_name")||text(item,"branch_name")||"company"}</span></div>)}</td><td>{text(user,"last_login_at")?new Date(text(user,"last_login_at")).toLocaleString():"Never"}</td><td>{canManage&&<div className={styles.actions}><button className={`${styles.btn} ${styles.secondary}`} onClick={()=>startAssignments(user)}>Access</button><button className={`${styles.btn} ${styles.secondary}`} onClick={()=>void action(user,"reset")}>Reset</button><button className={`${styles.btn} ${styles.secondary}`} onClick={()=>void action(user,"revoke")}>Revoke sessions</button>{text(user,"status")==="locked"&&<button className={`${styles.btn} ${styles.secondary}`} onClick={()=>void action(user,"unlock")}>Unlock</button>}{text(user,"status")==="suspended"?<button className={`${styles.btn} ${styles.secondary}`} onClick={()=>void action(user,"activate")}>Activate</button>:<button className={`${styles.btn} ${styles.danger}`} onClick={()=>void action(user,"suspend")}>Suspend</button>}</div>}</td></tr>)}</tbody></table></div></section></>;
}

function AssignmentEditor({assignments,catalog,update,remove}:{assignments:Assignment[];catalog:Catalog;update:(index:number,patch:Partial<Assignment>)=>void;remove:(index:number)=>void}){
  return <div className={styles.assignmentList}>{assignments.map((item,index)=>{const scope=roleScope(catalog,item.role_id);const sites=catalog.sites.filter(site=>!item.branch_id||num(site,"branch_id")===item.branch_id);return <div className={styles.assignment} key={index}><label className={styles.field}><span>Role</span><select value={item.role_id||""} onChange={e=>{const roleId=Number(e.target.value);const nextScope=roleScope(catalog,roleId);update(index,{role_id:roleId,branch_id:nextScope==="company"?null:item.branch_id,site_id:nextScope!=="site"?null:item.site_id});}}><option value="">Select role</option>{catalog.roles.map(role=><option key={num(role,"id")} value={num(role,"id")}>{text(role,"name")} · {text(role,"scope_level")}</option>)}</select></label><label className={styles.field}><span>Branch</span><select disabled={scope==="company"} value={item.branch_id??""} onChange={e=>update(index,{branch_id:e.target.value?Number(e.target.value):null,site_id:null})}><option value="">{scope==="company"?"Whole company":"Select branch"}</option>{catalog.branches.map(branch=><option key={num(branch,"id")} value={num(branch,"id")}>{text(branch,"name")}</option>)}</select></label><label className={styles.field}><span>Site</span><select disabled={scope!=="site"} value={item.site_id??""} onChange={e=>update(index,{site_id:e.target.value?Number(e.target.value):null})}><option value="">{scope==="site"?"Select site":"Not required"}</option>{sites.map(site=><option key={num(site,"id")} value={num(site,"id")}>{text(site,"name")}</option>)}</select></label><button type="button" className={`${styles.btn} ${styles.danger}`} onClick={()=>remove(index)}>Remove</button></div>;})}</div>;
}

function SecurityPanel({policy,canManage,onDone,setError}:{policy:Row|null;canManage:boolean;onDone:(m:string)=>void;setError:(m:string)=>void}){
  const [form,setForm]=useState<Row>(policy??{});useEffect(()=>setForm(policy??{}),[policy]);
  async function save(event:FormEvent){event.preventDefault();setError("");try{await api("/access/security-policy",{method:"PUT",body:JSON.stringify(form)});onDone("Security policy updated");}catch(err){setError(err instanceof Error?err.message:"Could not update policy");}}
  const numberFields:Array<[string,string]>=[["minimum_password_length","Minimum password length"],["password_history","Password history"],["lockout_attempts","Lockout attempts"],["lockout_minutes","Lockout minutes"],["session_hours","Session hours"],["idle_minutes","Idle timeout minutes"],["reset_token_minutes","Reset token minutes"],["max_active_sessions","Max active sessions"]];
  return <><section className={styles.hero}><div><span className={styles.badge}>Security controls</span><h1>Password, lockout and session policy.</h1><p>These settings are company-wide and apply to every BuildTrack login.</p></div></section><section className={styles.panel}><form className={styles.form} onSubmit={save}><div className={styles.grid2}>{numberFields.map(([key,label])=><label className={styles.field} key={key}><span>{label}</span><input type="number" value={String(form[key]??"")} disabled={!canManage} onChange={e=>setForm({...form,[key]:Number(e.target.value)})}/></label>)}</div><div className={styles.grid2}>{[["require_uppercase","Require uppercase"],["require_lowercase","Require lowercase"],["require_number","Require number"],["require_special","Require special character"]].map(([key,label])=><label className={styles.field} key={key}><span>{label}</span><select value={String(Boolean(form[key]))} disabled={!canManage} onChange={e=>setForm({...form,[key]:e.target.value==="true"})}><option value="true">Yes</option><option value="false">No</option></select></label>)}</div>{canManage&&<button className={`${styles.btn} ${styles.primary}`}>Save security policy</button>}</form></section></>;
}

function SessionsPanel({sessions,onDone,setError}:{sessions:Row[];onDone:(m:string)=>void;setError:(m:string)=>void}){
 async function revoke(id:number){setError("");try{await api<void>(`/access/sessions/${id}`,{method:"DELETE"});onDone("Session revoked");}catch(err){setError(err instanceof Error?err.message:"Could not revoke session");}}
 return <><section className={styles.hero}><div><span className={styles.badge}>Revocable sessions</span><h1>Your signed-in devices.</h1><p>BuildTrack stores only a SHA-256 hash of each opaque session token. Revoke anything you do not recognise.</p></div></section><section className={styles.panel}><div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Session</th><th>Address</th><th>Last seen</th><th>Expires</th><th>Status</th></tr></thead><tbody>{sessions.map(session=><tr key={num(session,"id")}><td><strong>#{num(session,"id")}</strong><div className={styles.muted}>{text(session,"user_agent").slice(0,80)}</div></td><td>{text(session,"ip_address")||"Unknown"}</td><td>{new Date(text(session,"last_seen_at")).toLocaleString()}</td><td>{new Date(text(session,"expires_at")).toLocaleString()}</td><td>{Boolean(session.current)?<span className={styles.sessionCurrent}>Current</span>:text(session,"revoked_at")?<span>Revoked</span>:<button className={`${styles.btn} ${styles.danger}`} onClick={()=>void revoke(num(session,"id"))}>Revoke</button>}</td></tr>)}</tbody></table></div></section></>;
}

function EventsPanel({events,users}:{events:Row[];users:Row[]}){return <><section className={styles.hero}><div><span className={styles.badge}>Security audit</span><h1>Authentication and account events.</h1><p>Successful and failed logins, lockouts, password recovery, session revocation and access changes are retained for investigation.</p></div></section><section className={styles.panel}>{events.length?events.map(event=><div className={styles.event} key={num(event,"id")}><span>{new Date(text(event,"occurred_at")).toLocaleString()}</span><strong>{text(event,"event_type").replaceAll("_"," ")}</strong><span>{text(users.find(user=>num(user,"id")===num(event,"user_id")),"full_name")||text(event,"username_attempted")||"System"} · {text(event,"ip_address")||"no IP"}</span></div>):<div className={styles.empty}>No security events yet.</div>}</section></>}

function ProfilePanel({user,onDone,setError}:{user:Row;onDone:(m:string)=>void;setError:(m:string)=>void}){const [current,setCurrent]=useState("");const [next,setNext]=useState("");const [confirm,setConfirm]=useState("");async function change(event:FormEvent){event.preventDefault();setError("");try{if(next!==confirm)throw new Error("Passwords do not match");await api("/access/change-password",{method:"POST",body:JSON.stringify({current_password:current,new_password:next})});setCurrent("");setNext("");setConfirm("");onDone("Password changed and other sessions revoked");}catch(err){setError(err instanceof Error?err.message:"Could not change password");}}return <><section className={styles.hero}><div><span className={styles.badge}>Personal security</span><h1>{text(user,"full_name")}</h1><p>{text(user,"email")} · {text(user,"job_title")||"BuildTrack user"}</p></div></section><section className={styles.panel}><div className={styles.panelHead}><div><h2>Change password</h2><p>Password history prevents recent passwords from being reused. Changing it revokes all other active sessions.</p></div></div><form className={styles.form} onSubmit={change}><label className={styles.field}><span>Current password</span><input type="password" value={current} onChange={e=>setCurrent(e.target.value)} required/></label><div className={styles.grid2}><label className={styles.field}><span>New password</span><input type="password" value={next} onChange={e=>setNext(e.target.value)} required/></label><label className={styles.field}><span>Confirm new password</span><input type="password" value={confirm} onChange={e=>setConfirm(e.target.value)} required/></label></div><button className={`${styles.btn} ${styles.primary}`}>Change password securely</button></form></section></>}
