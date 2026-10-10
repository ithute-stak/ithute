import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

const guides: Record<string,{title:string;intro:string;sections:{title:string;text:string;code?:string}[]}> = {
 "authentication": {title:"Authentication & OAuth",intro:"Use Ithute Auth for standards-based OAuth 2.0 authorization-code + PKCE.",sections:[
 {title:"Identity endpoints",text:"Use the approved central Ithute Auth issuer, not the developer portal host. Discovery and public signing keys are exposed by the issuer.",code:"GET /.well-known/openid-configuration\nGET /.well-known/jwks.json\nGET /oauth/authorize\nPOST /oauth/token"},
 {title:"OAuth client registration",text:"An authorized platform administrator registers the application, configures exact HTTPS callback URLs, and activates it. Wildcard redirect URLs are not permitted."},
 {title:"Protect server sessions",text:"Validate PKCE state, nonce, issuer, audience, signature and token expiry. Check central session status online, fail closed on outages, and enforce your own permissions."},
 {title:"Session endpoints",text:"The issuer supports checking online session status and revoking the current session.",code:"GET /v1/account/session-status\nPOST /v1/account/sessions/revoke-current"}
 ]},
 "nextjs":{title:"Next.js Auth SDK",intro:"Ithute Auth's App Router SDK supports server-controlled sessions and OAuth PKCE. Public npm installation is not yet available.",sections:[
 {title:"Package status",text:"The ithute-auth npm distribution is built and tested but not yet confirmed published to a public registry. The install commands below are previews, not instructions to run against npm today.",code:"# Planned after npm publishing\nnpm install ithute-auth\npnpm add ithute-auth"},
 {title:"Server-only environment",text:"Create an approved OAuth client and HTTPS callback. Keep all values except public documentation on the server.",code:"ITHUTE_AUTH_ISSUER=https://YOUR-APPROVED-ISSUER\nITHUTE_AUTH_CLIENT_ID=your-client-id\nITHUTE_AUTH_CALLBACK_URL=https://your-app.example/api/auth/ithute/callback\nITHUTE_AUTH_SESSION_SECRET=GENERATE_A_STRONG_32_BYTE_PLUS_SECRET"},
 {title:"Initialize authentication",text:"Use the official ithute-auth package export after publication. Until then, this is a reference integration example, not an executable npm quickstart.",code:'import { createIthuteAuth } from "ithute-auth";\n\nexport const auth = createIthuteAuth({\n  issuer: process.env.ITHUTE_AUTH_ISSUER!,\n  clientId: process.env.ITHUTE_AUTH_CLIENT_ID!,\n  callbackUrl: process.env.ITHUTE_AUTH_CALLBACK_URL!,\n  secret: process.env.ITHUTE_AUTH_SESSION_SECRET!,\n});'},
 {title:"Server-side API calls",text:"Use authenticatedRequest for /v1/account/ endpoints from server routes only. Never expose access tokens in client JavaScript.",code:'const result = await auth.authenticatedRequest("/v1/account/developer/access-requests");'}
 ]},
 "accounts-and-mail":{title:"Developer accounts and email",intro:"Register an identity using your existing email address. An identity alone does not create a mailbox or grant permissions.",sections:[
 {title:"Register",text:"Visit /developer/register. A valid Turnstile challenge and configured central Auth service are required. Verify ownership of your email before requesting product access."},
 {title:"Ithute mailbox",text:"An @ithute.co.ls mailbox currently requires a separate request and approved provisioning. Availability and ownership of a chosen address must be verified. Account registration is not mailbox creation."},
 {title:"Request integrations",text:"Sign in on /developer/dashboard to request Auth, email, DNS, push, or hosting access. A verified email is required; requests are reviewed by authorized administrators."}
 ]},
 "api-reference":{title:"API reference",intro:"Confirmed central identity endpoints. Managed products are not open-access public APIs.",sections:[
 {title:"Discovery",text:"Fetch issuer metadata and JWKS; keys and URLs are issuer-specific.",code:"GET /.well-known/openid-configuration\nGET /.well-known/jwks.json"},
 {title:"Sign-in and tokens",text:"OAuth authorization-code + PKCE with registered clients and exact callbacks.",code:"GET /oauth/authorize\nPOST /oauth/token"},
 {title:"Identity and sessions",text:"Registration is subject to abuse controls. Account API calls require a valid, active bearer session.",code:"POST /v1/users/register\nGET /v1/account/session-status\nPOST /v1/account/sessions/revoke-current"},
 {title:"Access requests",text:"Authenticated users may submit and list their own requests. The backend requires verified email for submissions and enforces request limits.",code:"GET /v1/account/developer/access-requests\nPOST /v1/account/developer/access-requests"},
 {title:"Protected services",text:"OAuth client administration, Push, DNS, mailbox provisioning, and infrastructure operations require additional product authorization. There are no generally available unrestricted developer credentials."}
 ]},
 "security":{title:"Security and deployment",intro:"Secure integrations must be verified before production rollout.",sections:[
 {title:"Infrastructure requirements",text:"Require HTTPS, approved exact OAuth redirects, strong server secrets, configured anti-bot verification and distributed registration rate limits."},
 {title:"Identity and account security",text:"Verify email ownership, support MFA, check online central session status, restrict grants by authorization and audit administrative changes."},
 {title:"Testing",text:"Test callback mismatch, cross-origin POST, revoked sessions, session expiry, central outages, email verification and request throttling."},
 {title:"Deployment",text:"Match the deployed image SHA to the approved release and verify actual production routes before announcing availability. Keep a rollback plan."}
 ]}
};
export async function generateStaticParams(){return Object.keys(guides).map(slug=>({slug}));}
export async function generateMetadata({params}:{params:Promise<{slug:string}>}):Promise<Metadata>{
 const {slug}=await params;return {title:guides[slug]?.title ? `${guides[slug].title} · Ithute Developer Docs` : "Documentation · Ithute"};
}
export default async function GuidePage({params}:{params:Promise<{slug:string}>}){
 const {slug}=await params;
 const guide=Object.prototype.hasOwnProperty.call(guides,slug)?guides[slug]:undefined;
 if(!guide)notFound();
 return <main className="min-h-screen bg-[#07101e] text-slate-100"><div className="mx-3 grid gap-8 px-4 py-10 lg:grid-cols-[250px_minmax(0,1fr)] lg:px-8">
  <aside className="lg:sticky lg:top-8 lg:self-start"><Link href="/developer" className="font-bold text-cyan-300">!thute / developer</Link><h2 className="mt-8 text-sm font-bold uppercase tracking-wider text-slate-400">Documentation</h2><nav aria-label="Developer guides" className="mt-4 space-y-1">{Object.entries(guides).map(([key,item])=><Link key={key} href={`/developer/docs/${key}`} aria-current={key===slug?"page":undefined} className={`block rounded-lg px-3 py-2 text-sm ${key===slug?"bg-cyan-400/15 font-bold text-cyan-300":"text-slate-300 hover:bg-white/10"}`}>{item.title}</Link>)}</nav></aside>
  <article className="max-w-5xl"><Link href="/developer/docs" className="text-sm text-cyan-300">← All developer documentation</Link><p className="mt-10 text-xs font-bold uppercase tracking-[.18em] text-cyan-300">Ithute developer documentation</p><h1 className="mt-3 text-4xl font-black sm:text-5xl">{guide.title}</h1><p className="mt-5 text-lg leading-8 text-slate-300">{guide.intro}</p>{guide.sections.map((section,i)=><section key={i} className="mt-10 border-t border-white/10 pt-8"><h2 className="text-2xl font-bold">{section.title}</h2><p className="mt-3 leading-7 text-slate-300">{section.text}</p>{section.code&&<pre className="mt-5 overflow-x-auto rounded-2xl border border-cyan-400/20 bg-[#0d1d30] p-5 text-sm leading-7 text-cyan-100"><code>{section.code}</code></pre>}</section>)}<p className="mt-12 text-sm text-slate-400">Documentation is maintained by Ithute. Product availability depends on authorized service access.</p></article>
 </div></main>;
}
