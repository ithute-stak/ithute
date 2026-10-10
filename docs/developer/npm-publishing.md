# Publishing ithute-auth

The package source is `packages/ithute-auth-nextjs`; its npm package name is now configured as `ithute-auth` in the draft packaging branch.

**This is not a publication record.** Registry ownership and the right to publish `ithute-auth` must be confirmed by the release administrator. Until npm reports a successful publish and an installation test passes, public documentation must continue to mark install commands as *planned*.

## Package build

```bash
cd packages/ithute-auth-nextjs
npm ci
npm run typecheck
npm test
npm pack --dry-run
```

The distribution uses compiled `dist/index.js` and `dist/index.d.ts`, not raw TypeScript source. The `prepack` hook runs typechecks, contract tests and compilation before packaging.

## Publication checklist

1. Confirm the `ithute-auth` name is available and you control it in the npm registry. Do not overwrite or impersonate an unrelated package.
2. Approve public licensing and legal notices. The manifest currently uses `UNLICENSED`, meaning publication needs explicit release/legal approval.
3. Add verified README examples and a versioned changelog; follow semver and release tags.
4. Run clean npm install + build against supported Next.js 15/16 in a minimal external fixture.
5. Inspect npm pack files for secrets, internal configuration, source maps and unpublished code.
6. Configure npm trusted publishing/OIDC for an approved release workflow, or arrange a secure manual publish by an authorized maintainer.
7. Publish an approved release and verify it from the public registry, then switch in-app documentation from planned to available.

Planned package usage after publication:

```bash
npm install ithute-auth
pnpm add ithute-auth
```

```ts
import { createIthuteAuth } from "ithute-auth";
```

Do not tell users to execute the planned install commands until publication is verified.
