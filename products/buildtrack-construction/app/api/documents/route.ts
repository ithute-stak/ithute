import { env } from "cloudflare:workers";
import { getChatGPTUser } from "../../chatgpt-auth";

const now = () => new Date().toISOString();

async function ensureCompany(db: D1Database) {
  let company = await db.prepare("SELECT id FROM companies ORDER BY id LIMIT 1").first<{ id: number }>();
  if (!company) {
    const timestamp = now();
    await db.prepare("INSERT INTO companies (name, country, currency, created_at, updated_at) VALUES (?, ?, ?, ?, ?)")
      .bind("My Construction Company", "Lesotho", "LSL", timestamp, timestamp).run();
    company = await db.prepare("SELECT id FROM companies ORDER BY id LIMIT 1").first<{ id: number }>();
  }
  if (!company) throw new Error("Unable to prepare the company workspace.");
  return company.id;
}

export async function GET() {
  const user = await getChatGPTUser();
  if (!user) return Response.json({ error: "Sign in is required." }, { status: 401 });
  if (!env.DB) return Response.json({ error: "The document register is unavailable." }, { status: 500 });

  const companyId = await ensureCompany(env.DB);
  const rows = await env.DB.prepare("SELECT id, owner_type, owner_id, file_name, content_type, created_at FROM documents WHERE company_id = ? ORDER BY created_at DESC")
    .bind(companyId).all();
  return Response.json({ documents: rows.results });
}

export async function POST(request: Request) {
  try {
    const user = await getChatGPTUser();
    if (!user) return Response.json({ error: "Sign in is required." }, { status: 401 });
    if (!env.DB || !env.BUCKET) throw new Error("The secure document store is unavailable.");

    const formData = await request.formData();
    const file = formData.get("file");
    const ownerType = String(formData.get("ownerType") ?? "general");
    const ownerId = Number(formData.get("ownerId")) || null;
    if (!(file instanceof File)) throw new Error("Choose a document to upload.");
    if (file.size > 20 * 1024 * 1024) throw new Error("Each document must be 20 MB or smaller.");

    const companyId = await ensureCompany(env.DB);
    const objectKey = `company-${companyId}/${ownerType}/${crypto.randomUUID()}-${file.name.replace(/[^a-zA-Z0-9._-]/g, "_")}`;
    await env.BUCKET.put(objectKey, await file.arrayBuffer(), { httpMetadata: { contentType: file.type || "application/octet-stream" } });

    const timestamp = now();
    const result = await env.DB.prepare("INSERT INTO documents (company_id, owner_type, owner_id, file_name, content_type, object_key, uploaded_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")
      .bind(companyId, ownerType, ownerId, file.name, file.type || null, objectKey, user.email, timestamp, timestamp).run();

    return Response.json({ ok: true, id: result.meta.last_row_id });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Unable to upload the document." }, { status: 400 });
  }
}
