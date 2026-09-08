import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const buildTrackTitle = /BuildTrack Construction Operations/i;

test("includes the BuildTrack application shell in the production bundle", async () => {
  const bundle = await readFile(new URL("../dist/server/index.js", import.meta.url), "utf8");
  assert.match(bundle, buildTrackTitle);
});
