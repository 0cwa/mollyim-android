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

Set `JAVA_HOME` and `ANDROID_HOME` to the actual installed directories before invoking Gradle. Replace the example paths for your machine:

```sh
export JAVA_HOME=/path/to/temurin-21
export ANDROID_HOME=/path/to/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
```

```sh
sdkmanager "platform-tools" "platforms;android-36.1" \
  "build-tools;36.0.0" "ndk;28.0.13004108"
```

Check the local versions with:

```sh
./gradlew --version
java -version
"$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" --list_installed
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

Run the replay-tool safety and portability tests from the primary checkout:

```sh
python3 -m unittest discover -s tools/827 -p 'test_*.py'
```

The refreshed series passes all 19 replay/tool tests, including the fresh Git configuration replay and a tamper-negative check that ensures the aapt2 equivalence fixture inputs match their pinned source blobs. Independent receipts are in `reports/827/independent/INDEPENDENT-REVIEW.md` and `reports/827/independent/`.

The explicit `--repo .` makes the script use this candidate checkout rather than its `origin` remote. A PASS means both independent patch applications produced identical Git trees and declared ownership checks passed. Replay supplies an explicit committer identity and disables commit signing. It skips LFS smudging, so hydrate and verify LFS files in the replay worktree before Android checks. Current replay reports, logs, and residual diffs are in `reports/827/replay/`.

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

On tree `e783cf54487a5b5d78c3241ec977fd8c8cd23f1d`, this task passed with no findings; its log is `reports/827/build/fastLint-replay-fixes-20261024.log` (SHA-256 `cb512b8ec093c5b01024921f27ce5fd9c0ea93a7fbc7bc6d6a2f7664bd60a983`). Current hosted CI status is in `reports/827/acceptance.json`.

For the URI suffix, UnifiedPush receiver, and F5 endpoint retry tests:

```sh
(cd "$REPLAY_WORKTREE" && ./gradlew --no-daemon --max-workers=1 --dependency-verification=strict \
  --init-script "$PRIMARY_CHECKOUT/tools/827/test-worker-heap.init.gradle" \
  -Dorg.gradle.jvmargs='-Xmx8g -Xms256m -XX:MaxMetaspaceSize=1g -Dcom.android.tools.r8.threadCount=1 -XX:+UnlockExperimentalVMOptions -XX:hashCode=3' \
  :Signal-Android:testPlayStagingDebugUnitTest \
  --tests org.thoughtcrime.securesms.util.UriUtilTest_isValidExternalUri \
  --tests org.thoughtcrime.securesms.keyvalue.UnifiedPushReceiverAvailabilityTest)
```

The current-source unfiltered staging suite passed all 25 selected cases (16 URI cases and 9 receiver cases), including the F5 changed-endpoint retry and idempotence tests. The final-source suite summary is `reports/827/build/full-staging-d998-20261024-final-summary.json`; hosted CI also passed its focused URI/UnifiedPush regression step in run 40111431112. A clean online clone should omit `--offline`; the local recorded run used a prepared dependency cache.

Run the complete Play Staging Debug unit-test suite and app lint with the recorded single 2 GiB test worker:

```sh
(cd "$REPLAY_WORKTREE" && ./gradlew --no-daemon --max-workers=1 --dependency-verification=strict \
  --init-script "$PRIMARY_CHECKOUT/tools/827/test-worker-heap.init.gradle" \
  -Dorg.gradle.jvmargs='-Xmx8g -Xms256m -XX:MaxMetaspaceSize=1g -Dcom.android.tools.r8.threadCount=1 -XX:+UnlockExperimentalVMOptions -XX:hashCode=3' \
  :Signal-Android:testPlayStagingDebugUnitTest :Signal-Android:ktlintCheck)
```

The refreshed source passed the unfiltered staging suite: 2,800 tests, 0 failures/errors, and 78 skipped across 251 suites. The run includes 16 URI suffix cases and 9 UnifiedPush receiver tests. Log and receipts: `reports/827/build/full-staging-d998-20261024-final.log` and `reports/827/build/full-staging-d998-20261024-final-summary.json` (log SHA-256 `221f5e7509a1e971c07489a313be48d6b6aa4b50b792e74a235a3ba50732fb52`). `:Signal-Android:ktlintCheck` also passes on the refreshed source; log `reports/827/build/ktlint-final-d998-20261024.log` (SHA-256 `6b0258f51b1fdd54dd40cf5e3476fa71f06c935d76eef2db45bbc4f9b81e5fa9`). `tools/827/test-worker-heap.init.gradle` sets one test fork to 2 GiB; use it for full test runs.

Run the release-source compile separately:

```sh
(cd "$REPLAY_WORKTREE" && ./gradlew --no-daemon --max-workers=1 --dependency-verification=strict \
  --init-script "$PRIMARY_CHECKOUT/tools/827/test-worker-heap.init.gradle" \
  -Dorg.gradle.jvmargs='-Xmx8g -Xms256m -XX:MaxMetaspaceSize=1g -Dcom.android.tools.r8.threadCount=1 -XX:+UnlockExperimentalVMOptions -XX:hashCode=3' \
  :Signal-Android:compileWebsiteProdReleaseSources)
```

This task passed with strict dependency verification on refreshed source commit `d99876269eb6556e37bb2d584ba08e8334e8e5db` (27 tasks executed, 204 up-to-date). Its report and log are `reports/827/build/compileWebsiteProdReleaseSources-fastlintfix-summary.json` and `reports/827/build/compileWebsiteProdReleaseSources-fastlintfix-20261024.log` (SHA-256 `c02f238cd01e28c0311a9dba738aacec757fd45eddc18871b18cf5f6defb2cac`). This compiles release sources only; it does not assemble or sign an APK.

Hosted workflow run 40111431112 passed source verification, inventory validation, two replays, LFS hydration, `ciRemote`, `:Signal-Android:assemblePlayProdDebug`, and focused URI/UnifiedPush regression tests. Full log: `reports/827/ci/40111431112.log`; run link and detailed status are in `reports/827/acceptance.json`.

## Upgrade simulation

1. Choose an exact new Signal base SHA and Molly target SHA. Fetch them, verify commit identities and ancestry, and save both in the experiment record.
2. Start a separate checkout. Keep the reviewed source checkout intact.
3. Update the manifest base only after checking patch applicability and provenance. Replay branding and UnifiedPush independently, then as an ordered series.
4. On conflicts, preserve the failed worktree and JSON report. Inspect patch provenance, owned paths, and the upstream API change. Adapt only with a narrow patch and behavioral evidence; do not resolve automatically with `--ours` or `--theirs`.
5. Re-run manifest validation, two clean replays, parity checks, security review, and applicable build/tests. Reproducible replay alone does not prove target parity or runtime equivalence.

## Conflict troubleshooting

Treat a replay failure as evidence. Check for a missing source object, patch checksum mismatch, dependency/order error, changed API context, or changed owned paths. Keep the failed worktree and report for inspection. Never reuse a dirty partial application as replay input. Update checksums only after a reviewed patch is finalized.

## Historical failed attempts

Earlier attempts are recorded for context, not as results for the current source. Run 40105996791 stopped during replay with `PATCH_FAILED`; the per-patch cause is unconfirmed. Run 40108357095 replayed successfully but failed `:fast-lint:fastLint` on three candidate findings, which patch 23 fixes. The earlier full project matrix stopped with exit 130 after disk exhaustion at 15/23 variants and 14 suites; it also had URI fixture failures since corrected. See `reports/827/ci/` and `reports/827/build/history/attempt20-retry2/`.

## Cleanup

After saving replay, build, test, and parity reports, remove the replay worktrees. Keep the primary checkout and its tracked evidence:

```sh
git worktree remove --force /tmp/molly827-run-1
git worktree remove --force /tmp/molly827-run-2
```

## Rollback

Replay worktrees are disposable; remove them after saving reports. To discard an experimental patch edit, restore that edit from a clean candidate checkout. Do not reset or rewrite the audited source commit. No upstream merge or release operation is part of this runbook.
