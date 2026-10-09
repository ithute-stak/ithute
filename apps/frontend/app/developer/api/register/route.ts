import { NextRequest, NextResponse } from "next/server";

/** Server-side identity registration proxy. No browser CORS or client-side secrets. */
export async function POST(request: NextRequest) {
  const requestOrigin=request.headers.get("origin");
  if (!requestOrigin || requestOrigin!==request.nextUrl.origin)
    return NextResponse.json({message:"Cross-origin registration rejected."},{status:403});
  const contentType=request.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().startsWith("application/json"))
    return NextResponse.json({message:"JSON registration required."},{status:415});
  const declaredSize=Number(request.headers.get("content-length") || 0);
  if (declaredSize>8192)
    return NextResponse.json({message:"Registration request is too large."},{status:413});
  let payload: unknown;
  try { payload=await request.json(); } catch {
    return NextResponse.json({message:"Invalid request."},{status:400});
  }
  if (!payload || typeof payload!=="object" || Array.isArray(payload)) return NextResponse.json({message:"Invalid request."},{status:400});
  const data=payload as Record<string, unknown>;
  const email=typeof data.email==="string"?data.email.trim():"";
  const display_name=typeof data.display_name==="string"?data.display_name.trim():"";
  const password=typeof data.password==="string"?data.password:"";
  const verificationToken=typeof data.verificationToken==="string"?data.verificationToken:"";
  if (!email || email.length>320 || !email.includes("@") || !display_name || display_name.length>160 || password.length<10 || password.length>128)
    return NextResponse.json({message:"Provide a valid name, email address and password of at least 10 characters."},{status:422});
  const captchaSecret=process.env.ITHUTE_DEVELOPER_TURNSTILE_SECRET;
  if (!captchaSecret) return NextResponse.json({message:"Public registration is not enabled yet."},{status:503});
  if (!verificationToken || verificationToken.length>4096)
    return NextResponse.json({message:"Please complete the security challenge."},{status:422});
  try {
    const challenge=await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method:"POST",
      headers:{"Content-Type":"application/x-www-form-urlencoded"},
      body:new URLSearchParams({secret:captchaSecret,response:verificationToken}),
      cache:"no-store",signal:AbortSignal.timeout(5000),
    });
    const outcome=await challenge.json() as {success?:boolean;hostname?:string};
    if (!challenge.ok || outcome.success!==true || outcome.hostname!==request.nextUrl.hostname)
      return NextResponse.json({message:"Security verification failed."},{status:403});
  } catch { return NextResponse.json({message:"Security verification is unavailable."},{status:503}); }
  const origin=process.env.ITHUTE_AUTH_INTERNAL_URL;
  if (!origin) return NextResponse.json({message:"Developer registration is not configured yet."},{status:503});
  let target: URL;
  try {
    target=new URL(origin);
    if (!["https:","http:"].includes(target.protocol) || target.username || target.password || target.search || target.hash || target.pathname!=="/")
      throw new Error("Invalid base URL");
  } catch {return NextResponse.json({message:"Developer registration service is not configured."},{status:503});}
  try {
    const response=await fetch(new URL("/v1/users/register",target),{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({email,display_name,password}),cache:"no-store",signal:AbortSignal.timeout(10000),
    });
    if (response.ok) return NextResponse.json({message:"Account created."},{status:201});
    if (response.status===409) return NextResponse.json({message:"This email address is already registered."},{status:409});
    if (response.status===422) return NextResponse.json({message:"Check your registration details."},{status:422});
    return NextResponse.json({message:"Registration is temporarily unavailable."},{status:503});
  } catch {
    return NextResponse.json({message:"Registration service is temporarily unavailable."},{status:503});
  }
}
