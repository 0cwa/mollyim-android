# Draft PR description — external research only

## Summary

This experiment packages selected Molly launcher artwork and UnifiedPush/MollySocket changes as 23 ordered, provenance-preserving mailbox patches on Signal `c47a74ba0961903eeaeda6d22347a990056c3e83`. Two isolated replays match projected source tree `e783cf54487a5b5d78c3241ec977fd8c8cd23f1d`, with 83 owned paths and no unowned changes. Resource comparison reports 1,241 exact changed-element matches plus one QR string whose runtime text matches by aapt2 proof across 33 locale files. The F5 endpoint-retry change is included in the patch series and replay.

## Verification status

The refreshed source passed the unfiltered Play Staging Debug unit suite: 2,800 tests, 0 failures/errors, and 78 skipped across 251 suites; the URI suffix and UnifiedPush receiver tests contributed 25 passing cases. The exact log and summary are `reports/827/build/full-staging-d998-20261024-final.log` and `reports/827/build/full-staging-d998-20261024-final-summary.json`. Patch 23 applies numeric API-level spellings and balances a quote whose compiled QR text is aapt2-equivalent. Current-source app ktlint, repository fast-lint, and `:Signal-Android:compileWebsiteProdReleaseSources` pass (27 tasks executed, 204 up-to-date). Hosted [CI run 40111431112](https://github.com/0cwa/mollyim-android/actions/runs/40111431112) also passes replay, build/test/lint/dependency checks, Play Prod Debug APK assembly, and focused URI/UnifiedPush regression tests. The full build across all variants remains unverified. Historical failed attempts and their evidence are summarized in [the runbook](RUNBOOK.md#historical-failed-attempts) and retained under `reports/827/ci/`.

No live Signal account, MollySocket service, API 33 privacy behavior, or physical-device notification flow was tested. This draft does not claim full Molly parity, feature acceptance, or security signoff. See `docs/827/RFC.md`, `docs/827/RUNBOOK.md`, `docs/827/SECURITY.md`, and `reports/827/acceptance.json`.

The source retains Firebase and other Google dependencies; the release-source compile is not a Google-free/FOSS build. One inherited availability risk also remains: linked-device registration can succeed remotely before prekey loading fails locally, leaving an orphaned server-side device. Recommended follow-up work is a recoverable/transactional provisioning path, plus live service and API 33 clipboard/privacy validation.

## Suggested next milestones

1. Have maintainers review patch ownership, adaptations, and security dispositions, especially the F7 orphan-device recovery path.
2. Run the full project matrix across supported variants and devices; the current evidence covers Play Staging Debug tests, selected release-source compilation, and a Play Prod Debug CI build, not every variant.
3. Validate live MollySocket/Signal flows and API 33+ lock-screen privacy behavior with test accounts and devices, then decide whether a Google-dependency-free build belongs in scope.

## Review request

Please assess whether this bounded patch queue is useful alongside the current fork workflow, whether the ownership and adaptation records are sufficient, and what evidence would be required for a maintainer trial. The development branch is pushed for review; no upstream pull request or merge is part of this draft.
