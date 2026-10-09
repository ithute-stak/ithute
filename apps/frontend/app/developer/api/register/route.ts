import { NextRequest, NextResponse } from "next/server";

/** Server-side identity registration proxy. No browser CORS or client-side secrets. */
export async function POST(request: NextRequest) {
  let payload: unknown;
  try { payload=await request.json(); } catch {
    return NextResponse.json({message:"Invalid request."},{status:400});
  }
  if (!payload || typeof payload!=="object" || Array.isArray(payload)) return NextResponse.json({message:"Invalid request."},{status:400});
  const data=payload as Record<string, unknown>;
  const email=typeof data.email==="string"?data.email.trim():"";
  const display_name=typeof data.display_name==="string"?data.display_name.trim():"";
  const password=typeof data.password==="string"?data.password:"";
  if (!email || email.length>320 || !email.includes("@") || !display_name || display_name.length>160 || password.length<10 || password.length>128)
    return NextResponse.json({message:"Provide a valid name, email address and password of at least 10 characters."},{status:422});
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
