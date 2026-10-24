# Draft PR description — external research only

## Summary

This proof of concept packages selected Molly launcher artwork and UnifiedPush/MollySocket changes as 20 ordered, provenance-preserving mailbox patches on Signal `c47a74ba0961903eeaeda6d22347a990056c3e83`. The replay tooling validates patch inputs, creates isolated worktrees, checks declared ownership, and compares two replay tree hashes. The current expected reconstructed tree is `f00af8f47e8f5bef1cb65559d0a8c7c45d2e5f77` at development HEAD `0e34c904f72fb899947967e5d2b37f78ca71b70e`.

## Review status

This is a draft handoff for maintainer feedback. The branch may be pushed for review, but no upstream pull request or merge has been submitted. It does not claim full Molly parity or feature acceptance. The previous full build stopped with exit 130 after disk exhaustion and recorded 30 `UriUtilTest_isValidExternalUri` fixture failures; the fixture has since been adapted. The final-head focused staging attempt compiled the changed tests, but all 17 cases stopped before assertions when an offline run could not fetch a Robolectric artifact; a retry with the configured dependency cache is in progress. Historical local API 30 synthetic flows predate the latest F4 fix. Live Signal/MollySocket, API 33 privacy metadata, and physical-device behavior remain untested. See `docs/827/RFC.md`, `docs/827/RUNBOOK.md`, and `reports/827/acceptance.json` for limits and evidence.

## Suggested review focus

Please assess whether a bounded patch queue is useful alongside the existing fork workflow, whether the selected feature boundary and adaptation records are appropriate, and whether the replay and ownership checks are sufficient for a maintainer trial. Security-sensitive runtime behavior still needs independent review and live integration evidence before feature acceptance.
