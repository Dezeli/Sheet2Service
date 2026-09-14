# Repository working agreements

- Propose the changes and commit message and obtain user approval before committing.
- Do not add Codex or another AI as author, co-author, or contributor. Use the user's configured Git identity; do not invent or override it.
- Use task branches for subsequent feature work when appropriate. Never push without user authorization.
- Stack: Django + Django REST Framework, React, PostgreSQL, served using Docker.
- Prefer deterministic code for parsing and validation; use Claude API for semantic inference.
- Keep analysis/model/configuration independent of the Preview runtime. Prefer a validated configurable template over arbitrary generated code.
- Never commit secrets or uploaded user data.
