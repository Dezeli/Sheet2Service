# Repository working agreements

- Propose the changes and commit message and obtain user approval before committing.
- Do not add Codex or another AI as author, co-author, or contributor. Use the user's configured Git identity; do not invent or override it.
- Use task branches for subsequent feature work when appropriate. Never push without user authorization.
- Stack: Django + Django REST Framework, React, PostgreSQL, served using Docker.
- Prefer deterministic code for parsing and validation; use Claude API for semantic inference.
- Keep analysis/model/configuration independent of the Preview runtime. Prefer a validated configurable template over arbitrary generated code.
- Never commit secrets or uploaded user data.
- Obtain explicit user approval before every Claude API call using the user's key, including tests, retries, and automated/background calls. Approval for implementation or key configuration is not approval to call the API. Before requesting approval, state the purpose, data to be sent, and planned call count; do not execute unapproved calls.
- Exception authorized by the user on 2026-10-10: clicking a clearly labeled app action such as "업로드하고 생성" or "Claude 호출하기" authorizes that action's single Claude call without a separate approval step. Display the purpose, data scope, and one-call notice before the action. This does not authorize agent-run tests, background calls, or automatic retries.
- Keep work in small, reviewable increments and pause after each agreed increment for user feedback.
- Initial input is CSV only; XLSX and sheet selection are deferred. Do not call Claude API for basic parsing or profiling.
- The user performs browser/UI verification. Do not run browser automation or inspect the UI unless explicitly requested. Use minimal relevant code checks to conserve tokens.
- The user will push commits themselves; do not push.
- Read `docs/handoff.md` when resuming work for current scope, decisions, and remaining work.
