# Molly #827 patch replay runbook

This runbook applies to the review branch `dev/molly-827-reproducible-poc` after it is available on the Molly repository. Clone the branch at full history depth (the default `git clone` is not shallow), including submodules:

```sh
git clone --branch dev/molly-827-reproducible-poc --recurse-submodules \
  https://github.com/0cwa/mollyim-android.git molly-827-reproducible-poc
cd molly-827-reproducible-poc
```

If using an automated checkout action, set `fetch-depth: 0` and enable recursive submodules. Use a disposable checkout with enough disk space; the full Android build writes substantial temporary and APK output.

Check that the checkout is on the review branch and clean before running the proof. The `origin` remote is expected to be the Molly repository in this clone; commands that replay patches explicitly use `--repo .` so they do not accidentally treat a source mirror as the working candidate.

```sh
git remote -v
git switch dev/molly-827-reproducible-poc
git status --short --branch
```

## Toolchain

The recorded environment used Gradle wrapper 9.4.1, JDK 21, Kotlin 2.2.20, Android Gradle Plugin 9.2.1, Android SDK API 36.1, Build Tools 36.0.0, and NDK 28.0.13004108. Install JDK 21 (for example, `openjdk-21-jdk` on Ubuntu), then install the Android packages through the SDK Manager. The wrapper pins Gradle; the project selects the matching SDK and NDK. For API 36.1 / Build Tools 36.0.0 / NDK 28.0.13004108, the command is:

```sh
sdkmanager "platform-tools" "platforms;android-36.1" \
  "build-tools;36.0.0" "ndk;28.0.13004108"
```

Check the local versions with:

```sh
./gradlew --version
java -version
${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin/sdkmanager --list_installed
```

## Verify source pins and checkout state

The expected audited candidate HEAD is `b8d5375b3fb6013f7939935ce73e250b53515381`; Signal base is `c47a74ba0961903eeaeda6d22347a990056c3e83`; Molly target is `0e202dda90785771ff8c87526eaaf30c655f54f3`. Fetch the public source refs if their objects are absent, then verify the full SHAs and ancestry before editing the manifest:

```sh
git fetch https://github.com/signalapp/Signal-Android.git c47a74ba0961903eeaeda6d22347a990056c3e83
git fetch https://github.com/0cwa/mollyim-android.git 0e202dda90785771ff8c87526eaaf30c655f54f3
git cat-file -e b8d5375b3fb6013f7939935ce73e250b53515381^{commit}
git cat-file -e c47a74ba0961903eeaeda6d22347a990056c3e83^{commit}
git cat-file -e 0e202dda90785771ff8c87526eaaf30c655f54f3^{commit}
git merge-base --is-ancestor c47a74ba0961903eeaeda6d22347a990056c3e83 0e202dda90785771ff8c87526eaaf30c655f54f3
```

Confirm that the audited candidate commit is present and is an ancestor of the review branch, then check the current revision and clean status before replay:

```sh
git cat-file -e b8d5375b3fb6013f7939935ce73e250b53515381^{commit}
git merge-base --is-ancestor b8d5375b3fb6013f7939935ce73e250b53515381 HEAD
git rev-parse HEAD
git status --short --branch
```

The PoC work branch is based on the audited candidate HEAD. Preserve that base; replay itself creates detached worktrees from the pinned Signal base.

## Validate and replay twice

Run the full replay and retain the machine report, logs, and residual diffs under `reports/827/replay/`. `replay_twice.py` invokes manifest validation itself, so this is the one-command replay:

```sh
python3 tools/827/replay_twice.py --repo . --manifest patches/827/series.yaml --worktree-prefix /tmp/molly827 --report reports/827/replay/replay-twice.json
```

The explicit `--repo .` is important: it uses this candidate checkout, not the checkout’s `origin` remote (which may point to a local source mirror). A PASS means both independent patch applications produced identical Git trees and the declared ownership checks passed. The first CI attempt passed manifest and inventory validation but returned `PATCH_FAILED` during replay 1, before Android checks. Its summarized log did not expose the per-patch `git am` diagnostic, so the exact cause remains unconfirmed. Replay now supplies explicit committer identity and disables commit signing; a fresh Git-config replay fixture passes. Separately, replay skips LFS smudging, so hydrate and verify LFS files in the replay worktree before build. CI run 40108357095 passed source validation, inventory validation, both replays, and LFS hydration, then failed `:fast-lint:fastLint` on three source findings. Patch 23 corrects those findings; rerun CI on the refreshed manifest before using its Android result. The per-run JSON and logs are in `reports/827/replay/` and `reports/827/ci/`. After preserving evidence, remove only the replay worktrees:

```sh
git worktree remove --force /tmp/molly827-run-1
git worktree remove --force /tmp/molly827-run-2
```

## Android build and tests

Inspect available tasks with `./gradlew tasks --all`. The project application module is `:Signal-Android`. **Run all Android Gradle checks from the reconstructed source worktree**, not from the metadata-rich primary checkout. Repository `fastLint` scans the source tree and will otherwise inspect evidence/log fixtures stored beside the primary source. Preserve the primary checkout path for the worker init script, then build from replay run 1:

```sh
PRIMARY_CHECKOUT="$(pwd)"
REPLAY_WORKTREE=/tmp/molly827-run-1
git -C "$REPLAY_WORKTREE" lfs checkout
git -C "$REPLAY_WORKTREE" lfs fsck
```

The branch workflow runs bounded CI checks and debug APK assembly from that reconstructed source tree with strict dependency verification:

```sh
(cd "$REPLAY_WORKTREE" && ./gradlew --no-daemon --max-workers=1 --dependency-verification=strict \
  --init-script "$PRIMARY_CHECKOUT/tools/827/test-worker-heap.init.gradle" \
  -Dorg.gradle.jvmargs='-Xmx8g -Xms256m -XX:MaxMetaspaceSize=1g -Dcom.android.tools.r8.threadCount=1 -XX:+UnlockExperimentalVMOptions -XX:hashCode=3' \
  ciRemote :Signal-Android:assemblePlayProdDebug)
```

Run repository fast-lint from the replay worktree as well:

```sh
(cd "$REPLAY_WORKTREE" && ./gradlew --offline --no-daemon --max-workers=1 --dependency-verification=strict \
  '-Dorg.gradle.jvmargs=-Xmx6g -Xms256m -XX:MaxMetaspaceSize=1g -Dcom.android.tools.r8.threadCount=1 -XX:+UnlockExperimentalVMOptions -XX:hashCode=3' \
  :fast-lint:fastLint)
```

After patch 23, this task passed on tree `e783cf54487a5b5d78c3241ec977fd8c8cd23f1d` with no findings; its log is `reports/827/build/fastLint-replay-fixes-20261024.log` (SHA-256 `cb512b8ec093c5b01024921f27ce5fd9c0ea93a7fbc7bc6d6a2f7664bd60a983`). The prior hosted run found the three source findings that patch 23 fixes. Final hosted CI and tests for the refreshed tree are still required.

For the URI suffix, UnifiedPush receiver, and F5 endpoint retry tests:

```sh
(cd "$REPLAY_WORKTREE" && ./gradlew --no-daemon --max-workers=1 --dependency-verification=strict \
  --init-script "$PRIMARY_CHECKOUT/tools/827/test-worker-heap.init.gradle" \
  -Dorg.gradle.jvmargs='-Xmx8g -Xms256m -XX:MaxMetaspaceSize=1g -Dcom.android.tools.r8.threadCount=1 -XX:+UnlockExperimentalVMOptions -XX:hashCode=3' \
  :Signal-Android:testPlayStagingDebugUnitTest \
  --tests org.thoughtcrime.securesms.util.UriUtilTest_isValidExternalUri \
  --tests org.thoughtcrime.securesms.keyvalue.UnifiedPushReceiverAvailabilityTest)
```

The selected F5 predecessor-source run passed 25/25 tests (16 URI cases and 9 receiver cases) before patch 23's lint-only/API-constant and quote-balancing corrections. Its file hashes, JUnit XML, and log hash are recorded in `reports/827/build/focused-test-results/f5-2g-summary.json`. The F5 source change is included in the current patch series. A clean online clone should omit `--offline`; this recorded run used the prepared dependency cache. Repeat this command on the refreshed replay worktree before treating it as final-source evidence.

Run the complete Play Staging Debug unit-test suite and app lint with the recorded single 2 GiB test worker:

```sh
(cd "$REPLAY_WORKTREE" && ./gradlew --no-daemon --max-workers=1 --dependency-verification=strict \
  --init-script "$PRIMARY_CHECKOUT/tools/827/test-worker-heap.init.gradle" \
  -Dorg.gradle.jvmargs='-Xmx8g -Xms256m -XX:MaxMetaspaceSize=1g -Dcom.android.tools.r8.threadCount=1 -XX:+UnlockExperimentalVMOptions -XX:hashCode=3' \
  :Signal-Android:testPlayStagingDebugUnitTest :Signal-Android:ktlintCheck)
```

On predecessor source commit `36578d8bb7058f862d5dd379440a12c1fbd7f3af`, app `:Signal-Android:ktlintCheck` passed and the final unfiltered staging suite passed 2,800 tests with 0 failures/errors and 78 skipped across 251 suites. The exact log is `reports/827/build/testPlayStagingDebug-full-final-2g-ktlint-20261024.log` and per-suite receipts are in `reports/827/build/full-f5-test-results/summary.json`. Patch 23 only applies lint conventions and quote balancing; aapt2 verifies the compiled QR string remains equivalent. Rerun the complete suite and lint on the refreshed replay tree before claiming final-source validation. Earlier 512 MiB and interrupted 2 GiB attempts remain historical failures. `tools/827/test-worker-heap.init.gradle` sets one test fork to 2 GiB; use it for full test runs.

The release-source compile task `:Signal-Android:compileWebsiteProdReleaseSources` passed with strict dependency verification on refreshed source commit `d99876269eb6556e37bb2d584ba08e8334e8e5db` (27 tasks executed, 204 up-to-date). Its report and log are `reports/827/build/compileWebsiteProdReleaseSources-fastlintfix-summary.json` and `reports/827/build/compileWebsiteProdReleaseSources-fastlintfix-20261024.log` (SHA-256 `c02f238cd01e28c0311a9dba738aacec757fd45eddc18871b18cf5f6defb2cac`). The predecessor-source compile also passed with 3 tasks executed/228 up-to-date. This compiles release sources only; it does not assemble or sign an APK. The current-source full staging suite still needs a rerun.

The earlier full project build at the audited source snapshot also stopped with exit 130 after disk exhaustion, reaching 15 of 23 variants and 14 test suites. It recorded 30 URI suffix fixture failures; the fixture is now adapted. That build did not cover the current 23-patch tree. See `/workspace/work/p2-baseline/attempt20-retry2-build-evidence-summary.json` and `reports/827/build/history/attempt20-retry2/`. No full project build has passed for the current source.

The first CI run (`40105996791`) passed manifest and inventory checks, then failed with `PATCH_FAILED` during replay before Android steps. The exact per-patch cause is unconfirmed. Replay now uses explicit Git committer identity and disables commit signing, backed by a fresh-config replay fixture. Separately, the workflow hydrates and checks LFS files in the replay worktree before screenshot validation. Corrected run 40108357095 passed source validation, replay, and LFS hydration, then failed `:fast-lint:fastLint` on three candidate-added findings, now addressed by patch 23. Confirm them on the new source worktree before retrying the full CI workflow. Review the current status and caveats in `reports/827/acceptance.json`.

## Upgrade simulation

1. Choose an exact new Signal base SHA and Molly target SHA. Fetch them, verify commit identities and ancestry, and save both in the experiment record.
2. Start a separate checkout. Keep the reviewed source checkout intact.
3. Update the manifest base only after checking patch applicability and provenance. Replay branding and UnifiedPush independently, then as an ordered series.
4. On conflicts, preserve the failed worktree and JSON report. Inspect patch provenance, owned paths, and the upstream API change. Adapt only with a narrow patch and behavioral evidence; do not resolve automatically with `--ours` or `--theirs`.
5. Re-run manifest validation, two clean replays, parity checks, security review, and applicable build/tests. Reproducible replay alone does not prove target parity or runtime equivalence.

## Conflict troubleshooting

Treat a replay failure as evidence. Check for a missing source object, patch checksum mismatch, dependency/order error, changed API context, or changed owned paths. Keep the failed worktree and report for inspection. Never reuse a dirty partial application as replay input. Update checksums only after a reviewed patch is finalized.

## Rollback

Replay worktrees are disposable; remove them with the two `git worktree remove` commands above after saving reports. To discard an experimental patch edit, restore that edit from a clean candidate checkout. Do not reset or rewrite the audited source commit. No upstream merge or release operation is part of this runbook.
