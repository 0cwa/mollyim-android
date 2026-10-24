# RFC: Reproducible Molly #827 feature reconstruction

**Status:** external proof of concept; maintainer review requested. No upstream PR or merge has been submitted.

## Problem

Molly-specific features can drift from the corresponding Signal release. A small, ordered patch series could make selected changes easier to replay and inspect. The experiment reconstructs two feature groups from a pinned Signal baseline: launcher artwork and UnifiedPush, including the MollySocket linked-device integration. This is a review of a bounded sample, not a claim of full Molly parity.

## Alternatives

1. **Merge-based fork:** retain Molly's existing fork and merge upstream Signal changes. It keeps familiar Git history and is straightforward for broad changes, while feature ownership and conflicts can be difficult to isolate across a large fork delta.
2. **Git-carrier:** retain the fork and use git-carrier to organize collaborative conflict resolution. This directly addresses coordination during rebases and remains useful alongside the experiment; it does not by itself make each feature a separately checksummed unit.
3. **Patch queue:** replay authored mailbox patches from an exact upstream SHA. This gives an explicit order, checksums, and feature boundaries, and makes clean replay measurable. The queue adds maintenance work and patches can still conflict or encode assumptions about APIs.

The PoC evaluates option 3 for the two selected features. A hybrid with the existing fork/git-carrier workflow is a plausible maintainer choice if the experiment proves useful; no migration is proposed.

## Proposed experiment

Use Signal baseline `c47a74ba0961903eeaeda6d22347a990056c3e83`, apply the current ordered patch series in `patches/827/series.yaml`, and compare declared paths or fragments with Molly target `0e202dda90785771ff8c87526eaaf30c655f54f3`. The current 20-patch manifest reconstructs tree `f00af8f47e8f5bef1cb65559d0a8c7c45d2e5f77` from the pinned base. The audited source commit remains `b8d5375b3fb6013f7939935ce73e250b53515381`; the current development head is `0e34c904f72fb899947967e5d2b37f78ca71b70e`. Each patch retains its source commit provenance. Replay reports, parity records, security review, and acceptance evidence are kept under `reports/827/` and associated project evidence.

## Scope and limits

The feature boundary is launcher artwork and selected UnifiedPush/MollySocket integration. Signal API adaptation and security fixes can differ from the Molly target; exceptions need explicit parity evidence and behavior tests. This does not port the full Molly feature set, prove runtime compatibility with deployed MollySocket or Signal services, establish production readiness, or prove APK reproducibility. Current acceptance remains incomplete. The previous full build stopped with exit 130 after disk exhaustion and recorded 30 `UriUtilTest_isValidExternalUri` fixture failures; the fixture has since been adapted for package suffixes, and the current focused staging sources compiled, but the first offline run could not fetch a required Robolectric artifact, so test assertions did not run; a dependency-cache retry is in progress. Live Signal/MollySocket/API 33 privacy behavior has not been tested. Historical API 30 synthetic flows are bounded evidence and predate the F4 locked callback fix. See `reports/827/acceptance.json`.

The development branch may be pushed to the Molly repository for review. No upstream pull request or merge is part of this work, and no production keys are used. No maintainer approval is claimed.
