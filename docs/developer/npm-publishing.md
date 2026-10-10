# Publishing ithute-auth

The package source is `packages/ithute-auth-nextjs`; its npm package name is now configured as `ithute-auth` on the merged main branch.

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
4. CI currently verifies an isolated packaged SDK consumer with Next.js 15 types; add a full Next.js browser-flow test and Next.js 16 compatibility before public release.
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

## Release authorization guardrails

Publishing to the public npm registry is a separate, privileged action. Do not commit npm authentication tokens or enable automatic publishing on pull requests. An authorized owner must verify package ownership, decide on a redistribution license, validate npm provenance/signing, and explicitly approve the release. The merged CI package-install tests do **not** establish that this registry name is owned or that the package has been published.

Once released, verify `npm view ithute-auth name version dist.integrity --json` and install that exact version in a new project from the public npm registry. Update the documentation site only after those checks pass.

## Manual public release workflow (after approval only)

The `.github/workflows/publish-ithute-auth-npm.yml` workflow must be run explicitly against `main` using workflow dispatch. It is not triggered by pushes or pull requests. It requires the literal dispatch confirmation `APPROVE_ITHUTE_AUTH_PUBLIC_RELEASE` and the GitHub `npm-production` environment.

**Before enabling this workflow**, a repository administrator must configure `npm-production` with required independent reviewers, prohibit self-approval where supported, and restrict deployment to `main`. Merely naming the environment in a workflow does NOT configure these controls. npm trusted publishing must be configured by the account authorized to control the `ithute-auth` npm package for this exact GitHub repository and workflow path. Never add an npm publish token to repository secrets or workflow files.

The workflow rejects unlicensed distributions using `release_preflight.py --strict`, performs tests and a compiled package build, checks for duplicate versions, and uses npm OIDC provenance. If any prerequisite is missing or the registry check is unavailable, publication must fail closed.

The workflow file being merged does **not** authorize a release. A human owner must approve the license, package name, release version, package files and npm publishing account. Before any real publication, verify the workflow's npm OIDC support and environment protection settings in the GitHub UI.

## Exact-version approval

The manual publication workflow requires an `expected_version` input that must exactly match the npm `package.json` version before publishing. Approvers should independently review both the release commit and package contents. A wrong or stale version stops the workflow; this input alone is not a substitute for configured environment reviewers or verified npm ownership.
