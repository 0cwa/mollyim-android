# Draft PR description — external research only

## Summary

This experiment packages selected Molly launcher artwork and UnifiedPush/MollySocket changes as 22 ordered, provenance-preserving mailbox patches on Signal `c47a74ba0961903eeaeda6d22347a990056c3e83`. Two isolated replays match projected source tree `26956e0f159c0b60719d4a20667aeef8913fa365`, with 83 owned paths and no unowned changes. Resource comparison matches all 1,242 changed elements across 33 locale files to the pinned Molly target. The F5 endpoint-retry change is included in the patch series and replay.

## Verification status

The selected staging tests passed 25/25 on the F5 working-tree snapshot: 16 URI suffix cases and 9 UnifiedPush receiver cases. App ktlint passed on the formatted source. The unfiltered staging suite passed 2,800 tests with no failures/errors (78 skipped) across 251 suites, and app ktlint passed. `:Signal-Android:compileWebsiteProdReleaseSources` also passed; this compiles release sources without assembling or signing an APK. An earlier 512 MiB run exhausted heap in AttachmentBackfill setup; the final 2 GiB run completed. The earlier full project build stopped with exit 130 after disk exhaustion; no full build on the current source has passed. The first GitHub Actions run failed at replay before Android checks; its exact `git am` cause is unconfirmed. The replay tool now sets explicit committer/signing configuration, and the workflow hydrates LFS files before screenshot checks. Corrected [CI run 40108357095](https://github.com/0cwa/mollyim-android/actions/runs/40108357095) has passed replay and pre-build validation; its Android checks are running.

No live Signal account, MollySocket service, API 33 privacy behavior, or physical-device notification flow was tested. This draft does not claim full Molly parity, feature acceptance, or security signoff. See `docs/827/RFC.md`, `docs/827/RUNBOOK.md`, `docs/827/SECURITY.md`, and `reports/827/acceptance.json`.

The source retains Firebase and other Google dependencies; the release-source compile is not a Google-free/FOSS build. One inherited availability risk also remains: linked-device registration can succeed remotely before prekey loading fails locally, leaving an orphaned server-side device. Recommended follow-up work is a recoverable/transactional provisioning path, plus live service and API 33 clipboard/privacy validation.

## Review request

Please assess whether this bounded patch queue is useful alongside the current fork workflow, whether the ownership and adaptation records are sufficient, and what evidence would be required for a maintainer trial. The branch may be pushed for review; no upstream pull request or merge is part of this draft.
