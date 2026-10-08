# Continuous integration

## Pull-request checks

`.github/workflows/ci.yml` runs on every pull request targeting `main`, pushes to `main`, merge-queue checks, and manual dispatch. There are no path filters: documentation-only changes still produce the required result.

The single job is named **FaultBrief CI**. It installs the recorded Node.js, Python, and pnpm versions, runs locked dependency setup, then executes:

```sh
pnpm run check
pnpm run smoke
```

These verify Prettier formatting, Ruff lint and formatting, backend integration tests, the production frontend build, TypeScript, and startup of the frontend/API/demo. No model provider, GPU, database, or deployment account is needed. Add browser tests and additional investigation/authorization tests to these commands when those features arrive.

Keep this job name stable. Branch protection requires this exact check; changing the name requires updating the protection rule.

## Workflow boundaries

- Runs use GitHub-hosted Ubuntu 24.04 workers and a 15-minute timeout.
- The workflow grants only `contents: read`. Checkout does not persist its Git credentials.
- Every external action is pinned to a full commit SHA, with a release comment. Dependabot proposes weekly action updates; review and verify new SHAs before merging.
- Pull requests use `pull_request`, with no `pull_request_target` execution of contributed code.
- CI uses blank/local environment examples and references no repository or environment secrets.
- Dependency caching is disabled for this initial workflow.
- Deployment belongs in a separate trusted workflow with a protected deployment environment. Do not add deployment credentials or cloud write permissions to this CI job.

These boundaries follow [GitHub's Actions security guidance](https://docs.github.com/en/actions/reference/security/secure-use).

## Protecting main

The desired configuration is versioned in `infra/github/main-protection.json`:

- Require **FaultBrief CI** from the GitHub Actions app (`app_id: 15368`).
- Require the pull request to be current with `main` before merging.
- Enforce checks for administrators as well as collaborators.
- Require pull requests, with zero independent approvals for this solo project. Increase the approval count when another reviewer joins.
- Disable force pushes and branch deletion.

Protection is a GitHub setting, not an effect of adding this JSON file. An administrator applies it once. Read the existing protection first and preserve any additional rules before reapplying this template:

```sh
gh api repos/Asharp97/FaultBrief/branches/main/protection
gh api --method PUT repos/Asharp97/FaultBrief/branches/main/protection --input infra/github/main-protection.json
```

A 404 on the first command means no branch-protection rule exists. A 403 means the authenticated client lacks repository administration access. See [GitHub's branch-protection documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

## Acceptance check

1. Open a test pull request with the CI workflow and confirm **FaultBrief CI** runs.
2. Introduce an intentionally unformatted JSON file in a new commit. Wait for the formatting step and required check to fail.
3. Confirm the pull request is blocked by the failed required check, including for the repository administrator. Do not attempt to bypass or actually merge the failing code.
4. Remove the intentional failure in a follow-up commit. Confirm all checks pass, leaving a reviewable CI change.

A local failing command proves failure propagation; the GitHub pull-request result and merge state prove enforcement. Do not report the latter as verified until it has actually been observed.
