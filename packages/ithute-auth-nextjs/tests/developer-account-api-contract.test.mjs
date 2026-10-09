import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { test } from "node:test";
const src=readFileSync(new URL("../src/index.ts",import.meta.url),"utf8");

test("account requests are server-only, verified and not generic proxy calls",()=>{
 assert.match(src,/import "server-only"/);
 assert.match(src,/async function authenticatedRequest\(/);
 assert.match(src,/path\.startsWith\("\/v1\/account\/"\)/);
 assert.match(src,/path\.includes\("%"\)/);
 assert.match(src,/jwtVerify\(session\.accessToken/);
 assert.match(src,/v1\/account\/session-status/);
 assert.match(src,/headers\.delete\("authorization"\)/);
 assert.match(src,/headers\.set\("Authorization"/);
 assert.match(src,/redirect:"error"/);
});
