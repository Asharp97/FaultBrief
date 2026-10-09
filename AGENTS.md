# FaultBrief repository rules

- Every response that reports repository changes must include a suggested commit message describing those changes. Include the checks actually run and any material limitation.
- Prefer Conventional Commit prefixes such as `feat:`, `fix:`, `docs:`, and `chore:`. Never claim a commit was created unless it was actually created.
- Do not create commits or push changes unless the user requests that action.
- Do not create per-feature branches unless the user explicitly requests one. Keep main's pull-request and required CI protection enabled; use an existing working branch for PRs.
- Preserve unrelated user changes. Read the current Git status before editing.
- Use pnpm for the frontend and uv for Python. Keep their lockfiles consistent with the manifests.
- Before using unfamiliar Next.js APIs, read the relevant guide bundled in `frontend/node_modules/next/dist/docs/` for the installed version. Keep agent instructions in this root file; automatic framework instruction generation is disabled.
- Keep actual credentials, private datasets, model artifacts, caches, and generated output out of Git. Environment examples must contain only placeholders or local defaults.
- This is a hiring-focused, read-only support investigation project. Build a small verified workflow before adding infrastructure or broad autonomous actions.
