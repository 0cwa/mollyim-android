# RFC: Reproducible Molly #827 feature reconstruction

**Status:** external proof of concept; maintainer review requested. No upstream PR or merge has been submitted.

## Problem

Molly-specific features can drift from the corresponding Signal release. A small, ordered patch series could make selected changes easier to replay and inspect. This experiment covers two feature groups from a pinned Signal baseline: launcher artwork and UnifiedPush, including MollySocket linked-device integration. It is a bounded sample, not a claim of full Molly parity.

## Alternatives

1. **Merge-based fork:** retain Molly's existing fork and merge upstream Signal changes. This preserves familiar Git history and supports broad changes, while feature ownership and conflicts can be difficult to isolate across a large fork delta.
2. **Git-carrier:** retain the fork and use git-carrier to coordinate conflict resolution. This helps during rebases and can complement the experiment, while not assigning each feature an independently checksummed unit.
3. **Patch queue:** replay authored mailbox patches from an exact upstream SHA. This records order, checksums, provenance, and feature boundaries, making clean replay measurable. The queue adds maintenance work and patches can still conflict or depend on particular APIs.

The proof of concept evaluates option 3 for the selected features. A hybrid with the current fork/git-carrier workflow is a possible maintainer choice if the evidence is useful; no migration is proposed.

## Proposed experiment

Use Signal baseline `c47a74ba0961903eeaeda6d22347a990056c3e83` and Molly target `0e202dda90785771ff8c87526eaaf30c655f54f3`. The refreshed 23-patch manifest reconstructs projected source tree `e783cf54487a5b5d78c3241ec977fd8c8cd23f1d` from the pinned base. Resource comparison reports 1,241 raw exact element matches and one aapt2-proven runtime-equivalent QR string among the 1,242 changed elements across 33 locale files; the rest of the application is not claimed to have full parity. The audited source commit is `b8d5375b3fb6013f7939935ce73e250b53515381`; the current feature source commit is `d99876269eb6556e37bb2d584ba08e8334e8e5db`. Prior green staging and release-source receipts are from predecessor source commit `36578d8bb7058f862d5dd379440a12c1fbd7f3af`; the later patch changes fast-lint conventions and quote balancing, with compiled QR text proven equivalent, and must be retested on the refreshed source tree. The F5 endpoint-retry change is included in the patch series and projected replay tree.

## Scope and limits

The feature boundary is launcher artwork and selected UnifiedPush/MollySocket integration. Signal API adaptations and security fixes can differ from the Molly target; each exception needs clear parity evidence and behavior tests. The PoC retains Firebase and other Google dependencies from its Signal-based source; `WebsiteProdRelease` source compilation does not establish a Google-free Molly/FOSS build. The PoC does not port the full Molly feature set, establish deployed-service compatibility, prove APK reproducibility, or establish production readiness. A known inherited risk remains in linked-device provisioning: if remote registration succeeds and local prekey loading then fails, an orphan linked device may remain on the server. A follow-up should make provisioning recoverable or clean up the remote device safely.

The selected F4/F5/F6 staging tests passed 25/25 cases on predecessor source commit `36578d8bb7058f862d5dd379440a12c1fbd7f3af`. App ktlint and the unfiltered staging suite passed on that source (2,800 tests, 0 failures/errors, 78 skipped across 251 suites). The current 23-patch source applies the repository's numeric API-level convention and quote balancing; aapt2 confirms the compiled QR text is unchanged. Current-source repository fast-lint passes on the replay tree with no findings (`reports/827/build/fastLint-replay-fixes-20261024.log`), and current-source `:Signal-Android:compileWebsiteProdReleaseSources` passes (27 tasks executed, 204 up-to-date) without assembling/signing an APK. The final-source full staging suite and hosted CI remain to be rerun. The full project build across all variants remains unverified. The earlier full project build stopped with exit 130 after disk exhaustion. The first CI run returned `PATCH_FAILED` before Android checks; its per-patch `git am` cause is unconfirmed. Replay now sets explicit committer identity and disables signing, and a fresh-config replay fixture passes. LFS hydration before screenshot validation is a separate preventive build-input step. Prior corrected CI run [40108357095](https://github.com/0cwa/mollyim-android/actions/runs/40108357095) passed source validation, patch validation, two replays, and LFS hydration, then failed at `:fast-lint:fastLint`; patch 23 addresses those three findings. A new hosted CI run has not completed. See `reports/827/ci/40108357095.log` and `reports/827/acceptance.json`. Live Signal/MollySocket/API 33 privacy and physical-device behavior remain untested.

The development branch may be pushed to the Molly repository for review. No upstream pull request or merge is part of this work; no production keys are used and no maintainer approval is claimed.
