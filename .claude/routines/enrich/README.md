# stock-enrich Routine — Operator Runbook

This routine runs the Phase 5 daily enrichment. Deploy once via the Claude Code Routines UI; it re-clones the repo each run.

## Prerequisites

1. **Claude Max 20x subscription** (routine consumes the same quota as interactive sessions).
2. **Claude Code on the web enabled** — `claude.ai/code` → Settings → Enable Claude Code on the web.
3. **GitHub fine-grained PAT**:
   - Go to `github.com/settings/personal-access-tokens`.
   - Resource owner: user/org owning this repo.
   - Repository access: **Only select repositories** → `stock` only.
   - Permissions:
     - Repository permissions → **Contents: Read and write**
     - Repository permissions → **Pull requests: Read and write**
     - Repository permissions → **Metadata: Read-only** (auto-granted)
     - Everything else: no access.
   - Expiration: ≤ 90 days (calendar reminder).
   - Copy the `github_pat_...` token exactly once.
4. **DART API key** from https://opendart.fss.or.kr — same key as `.env::DART_API_KEY`.

## Routine creation

1. Navigate to `claude.ai/code/routines` → **New routine**.
2. Name: `stock-enrich-daily`.
3. Prompt: use `.claude/routines/enrich/SKILL.md` from this repo (newer UIs auto-discover; older UIs: paste the body).
4. Repository: select this repo only.
5. Environment variables:
   - `GITHUB_TOKEN` = pasted fine-grained PAT.
   - `DART_API_KEY` = your DART key.
6. Setup script: `uv sync --extra ingest --extra collectors --extra dev`.
7. Trigger: Scheduled → daily → **22:00 UTC** (= 07:00 KST next day, per D-02).
8. **Branch push policy**: enable "Allow unrestricted branch pushes" IS NOT required (D-03 uses `claude/enrich-*` branches which match the default `claude/*` prefix — already allowed).
9. Allowed tools: Bash, Read, Edit, Write.
10. Network allowlist: `api.dart.fss.or.kr`, `github.com`, `api.github.com`.
11. Save → **Run now** once → inspect logs → confirm PR appears.

## GitHub repo configuration (one-time)

1. **Auto-merge**: repo Settings → General → scroll to "Pull Requests" → **Allow auto-merge** (checkbox).
2. **Branch protection on `main`** (Settings → Branches → Add rule for `main`):
   - Require a pull request before merging: on.
   - Require status checks to pass: on → add CI workflow (import_guard, pytest).
   - Require linear history: on (defense-in-depth against force-push).
3. **Auto-merge label**: Settings → Labels → New label `auto-merge` (description: "Trigger GitHub auto-merge once checks pass").
4. **Workflow to honor `auto-merge` label**: add `.github/workflows/auto-merge.yml` with action `pascalgn/automerge-action` gated on the label (separate plan if not present; this plan assumes the label alone is enough if auto-merge is configured via repo setting).

## Failure response table

| Failure | Detection | Action |
|---------|-----------|--------|
| Anthropic rate limit | `heartbeat.enrich.consecutive_failures >= 2` | Wait 1 day; if persists, move routine off-peak |
| Git push 401 | routine log | Rotate PAT; update env var |
| Git push conflict | routine log | Auto-retry with `git pull --rebase` (built into SKILL.md) |
| DART API key expired | `dart_structured_disagreement` spike | Rotate key in routine env var |
| Prompt injection match | `review_flags:["prompt_injection_suspected"]` count | Human reviews `backlog.md` |

## Security caveats

- Routines secrets are env vars visible to anyone with routine-edit rights (Anthropic does not yet ship a dedicated secrets store). Keep routine collaborators minimal.
- Fine-grained PAT is scoped to single repo with minimum permissions — if leaked, blast radius is bounded.
- Never commit PAT or DART key to the repo. `.env` is gitignored.

## Rotation calendar

- [ ] GitHub PAT: expires every ≤90 days; rotate.
- [ ] DART API key: 365-day validity; renew annually.
