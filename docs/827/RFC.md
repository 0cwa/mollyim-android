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

Use Signal baseline `c47a74ba0961903eeaeda6d22347a990056c3e83` and Molly target `0e202dda90785771ff8c87526eaaf30c655f54f3`. The current 22-patch manifest reconstructs projected source tree `26956e0f159c0b60719d4a20667aeef8913fa365` from the pinned base. Resource parity checks also match 1,242 changed elements across 33 locale files to the pinned target; the rest of the application is not claimed to have full parity. The audited source commit is `b8d5375b3fb6013f7939935ce73e250b53515381`; the feature source commit is `36578d8bb7058f862d5dd379440a12c1fbd7f3af`, preceded by metadata commit `7eda9c55e0fe124da682f6c2a4e49493cd665d97`. The F5 endpoint-retry change is included in the 22-patch series and projected replay tree.

## Scope and limits

The feature boundary is launcher artwork and selected UnifiedPush/MollySocket integration. Signal API adaptations and security fixes can differ from the Molly target; each exception needs clear parity evidence and behavior tests. This does not port the full Molly feature set, establish deployed-service compatibility, prove APK reproducibility, or establish production readiness.

The selected F4/F5/F6 staging tests passed 25/25 cases on their recorded working-tree snapshot. App ktlint passed on the formatted source commit. A broader staging suite hit test-worker memory exhaustion on the first attempt; a 2 GiB rerun on the final source is in progress. The earlier full project build stopped with exit 130 after disk exhaustion. The first CI run returned `PATCH_FAILED` before Android checks; its per-patch `git am` cause is unconfirmed. Replay now sets explicit committer identity and disables signing, and a fresh-config replay fixture passes. LFS hydration before screenshot validation is a separate preventive build-input step. The corrected CI run and a full current-head build remain outstanding. Live Signal/MollySocket/API 33 privacy and physical-device behavior remain untested. See `reports/827/acceptance.json` for criterion-by-criterion evidence.

The development branch may be pushed to the Molly repository for review. No upstream pull request or merge is part of this work; no production keys are used and no maintainer approval is claimed.
