# AGENTS.md — mollyim-android (0cwa fork)

These rules add to `~/.codex/AGENTS.md`. Where they conflict, this file wins for this repository.
Explicit instructions from me in the session win over both.

## Roles

- **Me / I**: the contributor. A PR's first-person voice is mine.
- **You**: the AI team (orchestrator plus subagents) assisting me.
- **Molly maintainers**: review proposals and decide what goes upstream. Never contact them, and never open
  a PR or issue on `github.com/mollyim/*`, unless I authorize the exact text.

## Where the work lives

This checkout is a shallow clone of Molly `main`. The real work is on branches of
`https://github.com/0cwa/mollyim-android` (remote `mine`):

| Branch | Purpose |
|---|---|
| `patch-release/molly-signal-8.33.2` | PR #10: Molly 8.19.2-4 applied to Signal 8.33.2 as a patch series |
| `upstream/signal-8.33.2`, `upstream/signal-8.19.2` | plain Signal trees |
| `patch-release/molly-8.19.2-4`, `port/molly-signal-8.33.2` | earlier stages of the same pipeline |
| `dev/molly-827-*`, `refactor/827-*`, `poc/*` | #827 research; preserve, don't rewrite |

Molly's own upstream branches (`origin`): `signal-8.20.4`, `upstream-stable`, `upstream-main`,
`fix/socks-proxy-dns-leak`, and others. Molly's own ports are the reference for what a minimal port looks like.

### Patch-release branch layout (PR #10)

- The tracked tree is **Signal's** tree. The Molly app is rebuilt from patches.
- `patches/molly/`: Molly's original patchset. **Never edit it and never review it.** It must stay byte-identical.
- `patches/ports/signal-<ver>/{initial,followups}/`: the AI compatibility layers. These are the only thing we refine.
- `molly-build.json`: pins (Signal commit, Molly target, `target_tree`, Android SDK, Gradle tasks and tests).
- `patches/ports/signal-<ver>/provenance.json`: per-layer `source_commit`, `before_tree`/`after_tree`,
  `mailbox_bytes`, bundle prerequisite, bundle sha256, and `mailbox_sha256`.
- Each follow-up is a chain link: a `source-checkpoint.bundle` (ref `refs/heads/source-checkpoint/<name>`,
  prerequisite = previous checkpoint) plus a mailbox built with
  `git format-patch --stdout --abbrev=8 -1 <commit>`, with a `Source-Commit: <commit>` line inserted after
  `Based-On-Source-Commit:`. Editing a follow-up in the middle of the chain changes every later checkpoint:
  replay the later ones, then regenerate their mailboxes, bundles and all pins (including `target_tree` and
  the hashes in `docs/PATCH-PIPELINE.md`). Never hand-edit a hash; compute it.

## What we are optimizing for

Make the **smallest change to Molly's patchset** that gives a working build on the new Signal version, while
keeping Molly's behavior and policies. In order:

1. **Check Molly's own work first.** Before writing or keeping an AI compatibility fix, check Molly's upstream
   branches (`signal-8.20.4`, `upstream-stable`, and so on) for an equivalent fix. Prefer Molly's version when
   it's as good or better.
2. **Minimize mechanically, not by reading.** For each compatibility hunk, revert it in a scratch tree and run
   the cheapest gate that could fail (compile or resource-link of the affected module). Keep the revert if the
   gate still passes. Report results per hunk. "No reduction found in the areas inspected" is not a result.
3. Don't count a diff reduction that removes retained Molly code or reverses an exclusion Molly made.
4. Report line counts against both the mechanical merge and Molly's source, before and after.

## Verification gates (required)

Run the preflight in the patch-release worktree before **every** push:

```sh
export JAVA_HOME=$HOME/.local/opt/jdk-21.0.13+9 PATH=$HOME/.local/opt/jdk-21.0.13+9/bin:$PATH \
       ANDROID_HOME=$HOME/Android/Sdk MOLLY_PREFLIGHT_DIR=$HOME/agent-scratch/mollyim-android/preflight
tools/patches/preflight.sh            # ~2 min: patch-tool tests + source reconstruction/tree proof
tools/patches/preflight.sh resources  # + Android resource linking; required for any res/ or layout change
tools/patches/preflight.sh full       # + assemble and the profile's regression tests, same as CI
```

- These check the same things CI checks. Missing `Source-Commit` trailers, short tree hashes and missing
  `@color`/`@string` references must be caught here, not in CI.
- **Batch fixes; push once.** Each push cancels the in-progress Android job, which takes about 22 minutes.
- **A task is done only when CI is green on the final pushed head.** If CI is still running, wait with
  `gh run watch` or say clearly that the result is pending. Never describe pending or skipped checks as passing.
  If CI fails after you report, fixing it comes before any new work.
- Only claim a check passed if you ran it and saw the output. "Static checks" that aren't the real build tool
  don't count.

## Orchestration

- One task per subagent. Close it when it reports back. Start a fresh agent for an unrelated follow-up instead
  of reusing a long-lived one.
- Use **Terra 6.1** for most subagents: medium for scouting and mechanical work, high for code changes and
  reviews. Use Sol (or Luna on max) only for a single bounded review of a hard decision, with all context
  supplied up front. This replaces the global "luna on max" preference for this repository.
- Wait for subagents in long blocks (several minutes). Don't call `wait_agent` every 20 seconds.
- Give each agent that edits files its own worktree. Only the orchestrator integrates into the shared branch:
  manifests, `provenance.json`, `molly-build.json`, the series file and docs.
- When I give a new instruction, assign it to one owner. Don't send it to every running agent.
- To read GitHub, use `gh pr view|checks|diff`, `gh run view|list|watch`, or `gh api -X GET ...`.
  Those forms are pre-approved and skip auto-review.

## Goal mode

- Pre-authorized: fetching source from `github.com/mollyim`, `github.com/signalapp` and `github.com/0cwa`;
  downloading toolchains (JDK, Android SDK components, Gradle dependencies); pushing to the 0cwa PR branch
  I named for the task.
- Not authorized without asking: opening PRs or issues upstream, merging, release signing, force-pushing
  shared branches, rewriting `dev/*` research branches.
- At the **first** real blocker that I can resolve (authorization, credentials, a choice between options),
  ask me. Don't spend more turns searching for a workaround.
- Track token use. If a phase uses much more than planned, stop and tell me why before continuing.

## Disk

Follow the disk rules in `~/.codex/AGENTS.md`. In addition, `/var/home` is btrfs and has run out of
**metadata** with ~200 GB showing free (Oct 2026), which made every write fail. Run `agent-disk-check` before
large checkouts or Gradle builds. Prefer `--filter=blob:none` clones. Remove preflight and scratch worktrees
with `git worktree remove` when done.

## This file

Upstream Molly is not agent-driven, so never commit `AGENTS.md` to a work or PR branch. It is listed in
`.git/info/exclude`, and its only tracked copy is the orphan branch `agent-config` on `mine`. To install it
in a new clone or worktree, run `git fetch mine agent-config && git show FETCH_HEAD:AGENTS.md > AGENTS.md`
and add `AGENTS.md` to that clone's `.git/info/exclude`. Commit changes to it only on `agent-config`.
