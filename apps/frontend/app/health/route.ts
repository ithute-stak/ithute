export function GET() {
  return Response.json({ service: "ithute-web", status: "ok" }, { status: 200 });
}
