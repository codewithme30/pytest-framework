<!-- Author: Anil Kalisetti -->
# Contributing

1. `make install-dev` (installs tools and the pre-commit hook).
2. Branch from `main`; keep changes small and focused.
3. Every Python file starts with a docstring header including `Author`.
4. Prefer simple, readable code; comment only what is genuinely non-obvious.
5. Add or update tests; `make unit data db` must pass offline.
6. `make lint typecheck` must be clean before opening a PR.
7. Never commit secrets. Secrets come from environment variables only.
