# Local sync — pulling Routine enrichment into your local clone

The Phase 5 enrichment Routine runs in an Anthropic Routines container,
commits `_derived` blocks to vault Markdown, opens a PR, and auto-merges
to `main`. Your local clone does **not** see those changes until you pull.

This document covers two ways to keep local in sync:

1. **Manual:** `uv run stock sync` (one-shot, run before opening Obsidian
   or starting `stock-mcp`).
2. **Background:** systemd user timer that runs `stock sync --reingest
   --quiet` every 30 minutes.

## 1. Manual sync — `stock sync`

```bash
uv run stock sync                 # fast-forward main, do not touch DB
uv run stock sync --reingest      # also re-run `stock ingest run` so Postgres
                                  # chunks/embeddings reflect the new _derived
uv run stock sync --branch main --remote origin   # explicit defaults
uv run stock sync --quiet         # suppress JSON report (cron-friendly)
```

**Behavior summary:**

| Local state vs. `origin/main` | Result | Exit code |
|------|--------|-----------|
| Working tree dirty | refuses, lists offending files | 1 |
| Up-to-date | no-op (still runs reingest if asked) | 0 |
| Behind only | fast-forward merge | 0 |
| Ahead only | no-op (you have unpushed local commits) | 0 |
| Diverged (ahead AND behind) | refuses, asks for manual rebase/merge | 1 |
| Fetch failed (network, auth) | error report on stderr | 1 |
| Reingest step failed | error report on stderr | 2 |

The command never merges, never rebases, never force-pushes. It only
fast-forwards. This is intentional — the Routine is the *only* writer of
`_derived`, so local should always be a strict subset of `origin/main`
unless you've made unrelated local commits.

## 2. systemd user timer (Linux / WSL)

Drop these two files into `~/.config/systemd/user/`:

### `~/.config/systemd/user/stock-sync.service`

```ini
[Unit]
Description=Pull Routine enrichment into local stock-wiki vault
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=%h/path/to/stock        # CHANGE ME
EnvironmentFile=%h/path/to/stock/.env    # CHANGE ME (DATABASE_URL etc.)
ExecStart=/usr/bin/env uv run stock sync --reingest --quiet
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

### `~/.config/systemd/user/stock-sync.timer`

```ini
[Unit]
Description=Run stock-sync every 30 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=30min
AccuracySec=1min
Persistent=true
Unit=stock-sync.service

[Install]
WantedBy=timers.target
```

### Enable

```bash
systemctl --user daemon-reload
systemctl --user enable --now stock-sync.timer

# Verify
systemctl --user list-timers stock-sync.timer
journalctl --user -u stock-sync.service -n 30        # recent run logs
```

### Manual one-off (without timer)

```bash
systemctl --user start stock-sync.service
journalctl --user -u stock-sync.service -n 30
```

## 3. macOS — launchd alternative

```xml
<!-- ~/Library/LaunchAgents/com.stockwiki.sync.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.stockwiki.sync</string>
    <key>ProgramArguments</key>
    <array>
      <string>/usr/bin/env</string>
      <string>uv</string>
      <string>run</string>
      <string>stock</string>
      <string>sync</string>
      <string>--reingest</string>
      <string>--quiet</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOU/path/to/stock</string>
    <key>StartInterval</key>
    <integer>1800</integer>
    <key>StandardOutPath</key>
    <string>/tmp/stock-sync.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/stock-sync.err</string>
  </dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.stockwiki.sync.plist
```

## 4. WSL note

If running this from WSL on top of a `/mnt/c/...` path, line endings can
diverge between local edits (CRLF auto-conversion) and the
container-merged commits (LF). If `git status` shows phantom diffs
across the board after a sync, set:

```bash
git config core.autocrlf false
git config core.eol lf
```

inside the repo, then `git checkout -- .` once to normalize.

## 5. Recovering from divergence

If `stock sync` reports `diverged`:

```bash
git status                            # see your local commits
git log --oneline origin/main..HEAD   # what's only local
git log --oneline HEAD..origin/main   # what's only remote (Routine commits)

# If your local commits are intentional and you want them on top of remote:
git fetch origin main
git rebase origin/main
git push origin main                  # branch protection requires PR — see below

# Or, simplest: open a PR for your local work and let it merge through
# the same auto-merge gate the Routine uses.
```

If branch protection blocks direct push (it does on `main`), make a
feature branch and PR your changes:

```bash
git checkout -b fix/local-edits
git push -u origin fix/local-edits
gh pr create --base main --title "..." --body "..." --label auto-merge
```
