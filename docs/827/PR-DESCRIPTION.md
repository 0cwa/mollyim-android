# Draft PR description — external research only

## Summary

This experiment packages selected Molly launcher artwork and UnifiedPush/MollySocket changes as 23 ordered, provenance-preserving mailbox patches on Signal `c47a74ba0961903eeaeda6d22347a990056c3e83`. Two isolated replays match projected source tree `e783cf54487a5b5d78c3241ec977fd8c8cd23f1d`, with 83 owned paths and no unowned changes. Resource comparison reports 1,241 exact changed-element matches plus one QR string whose runtime text matches by aapt2 proof across 33 locale files. The F5 endpoint-retry change is included in the patch series and replay.

## Verification status

The selected staging tests passed 25/25 on predecessor source commit `36578d8bb7058f862d5dd379440a12c1fbd7f3af`: 16 URI suffix cases and 9 UnifiedPush receiver cases. App ktlint and the unfiltered staging suite passed on that source (2,800 tests; 0 failures/errors; 78 skipped across 251 suites). Patch 23 applies numeric API-level spellings and balances a quote whose compiled QR text is aapt2-equivalent. On current source, repository fast-lint passes from the replay tree and `:Signal-Android:compileWebsiteProdReleaseSources` passes (27 tasks executed, 204 up-to-date); no APK is assembled or signed. The full staging suite and hosted CI still need reruns on the refreshed source. An earlier 512 MiB run exhausted heap in AttachmentBackfill setup; the final 2 GiB predecessor-source run completed. The earlier full project build stopped with exit 130 after disk exhaustion; no full build across all variants has passed. The first GitHub Actions run failed at replay before Android checks; its exact `git am` cause is unconfirmed. Prior CI run 40108357095 replayed and validated the manifest, then failed `:fast-lint:fastLint` on three candidate-added findings, now addressed in patch 23. See `reports/827/ci/40108357095.log`.

No live Signal account, MollySocket service, API 33 privacy behavior, or physical-device notification flow was tested. This draft does not claim full Molly parity, feature acceptance, or security signoff. See `docs/827/RFC.md`, `docs/827/RUNBOOK.md`, `docs/827/SECURITY.md`, and `reports/827/acceptance.json`.

The source retains Firebase and other Google dependencies; the release-source compile is not a Google-free/FOSS build. One inherited availability risk also remains: linked-device registration can succeed remotely before prekey loading fails locally, leaving an orphaned server-side device. Recommended follow-up work is a recoverable/transactional provisioning path, plus live service and API 33 clipboard/privacy validation.

## Review request

Please assess whether this bounded patch queue is useful alongside the current fork workflow, whether the ownership and adaptation records are sufficient, and what evidence would be required for a maintainer trial. The branch may be pushed for review; no upstream pull request or merge is part of this draft.
