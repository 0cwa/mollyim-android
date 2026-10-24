# Molly #827 patch replay runbook

This runbook applies to the review branch `dev/molly-827-reproducible-poc` after it is available on the Molly repository. Clone the branch at full history depth (the default `git clone` is not shallow), including submodules:

```sh
git clone --branch dev/molly-827-reproducible-poc --recurse-submodules \
  https://github.com/0cwa/mollyim-android.git molly-827-reproducible-poc
cd molly-827-reproducible-poc
```

If using an automated checkout action, set `fetch-depth: 0` and enable recursive submodules. Use a disposable checkout with enough disk space; the full Android build writes substantial temporary and APK output.

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

The explicit `--repo .` is important: it uses this candidate checkout, not the checkout’s `origin` remote (which may point to a local source mirror). A PASS means both independent patch applications produced identical Git trees and the declared ownership checks passed. The first CI attempt passed manifest and inventory validation but returned `PATCH_FAILED` during replay 1, before Android checks. Its summarized log did not expose the per-patch `git am` diagnostic, so the exact cause remains unconfirmed. Replay now supplies explicit committer identity and disables commit signing; a fresh Git-config replay fixture passes. Separately, replay skips LFS smudging, so the workflow runs `git lfs checkout` and `git lfs fsck` in the replay worktree before screenshot validation/build. The corrected current-head CI run is pending; see run 40105996791 for the initial failure. It does not establish application behavior or a successful Android build. The per-run JSON and logs are in the same report directory. After preserving evidence, remove only the replay worktrees:

```sh
git worktree remove --force /tmp/molly827-run-1
git worktree remove --force /tmp/molly827-run-2
```

## Android build and tests

Inspect available tasks with `./gradlew tasks --all`. The project application module is `:Signal-Android`. The branch workflow runs the bounded CI checks and debug APK assembly with strict dependency verification:

```sh
./gradlew --no-daemon --max-workers=2 --dependency-verification=strict \
  --init-script tools/827/test-worker-heap.init.gradle \
  -Dorg.gradle.jvmargs='-Xmx8g -Xms256m -XX:MaxMetaspaceSize=1g -Dcom.android.tools.r8.threadCount=1 -XX:+UnlockExperimentalVMOptions -XX:hashCode=3' \
  ciRemote :Signal-Android:assemblePlayProdDebug
```

For the URI suffix, UnifiedPush receiver, and F5 endpoint retry tests:

```sh
./gradlew --offline --no-daemon --max-workers=1 --dependency-verification=strict \
  --init-script tools/827/test-worker-heap.init.gradle \
  -Dorg.gradle.jvmargs='-Xmx8g -Xms256m -XX:MaxMetaspaceSize=1g -Dcom.android.tools.r8.threadCount=1 -XX:+UnlockExperimentalVMOptions -XX:hashCode=3' \
  :Signal-Android:testPlayStagingDebugUnitTest \
  --tests org.thoughtcrime.securesms.util.UriUtilTest_isValidExternalUri \
  --tests org.thoughtcrime.securesms.keyvalue.UnifiedPushReceiverAvailabilityTest
```

The selected F5 working-tree run passed 25/25 tests (16 URI cases and 9 receiver cases). Source file hashes, JUnit XML, and log hash are recorded in `reports/827/build/focused-test-results/f5-2g-summary.json`. The F5 source change is included in patch 22 and the current projected replay tree.

App `:Signal-Android:ktlintCheck` passed on the formatted source (`reports/827/build/ktlint-f5-formatted-20261024.log`). The full staging unit suite has not completed. The first attempt ran with the default 512 MiB test worker and stopped with exit 130 after repeated heap exhaustion in AttachmentBackfill MockK setup. A second 2 GiB attempt was stopped before results while the patch set was being updated; the final source run is now active at `reports/827/build/testPlayStagingDebug-full-final-2g-ktlint-20261024.log`. `tools/827/test-worker-heap.init.gradle` sets one test fork to 2 GiB; use it for full test runs.

The earlier full project build at the audited source snapshot also stopped with exit 130 after disk exhaustion, reaching 15 of 23 variants and 14 test suites. It recorded 30 URI suffix fixture failures; the fixture is now adapted. That build did not cover the current 22-patch tree. See `/workspace/work/p2-baseline/attempt20-retry2-build-evidence-summary.json` and `reports/827/build/history/attempt20-retry2/`. No full project build has passed for the current source.

The first CI run (`40105996791`) passed manifest and inventory checks, then failed with `PATCH_FAILED` during replay before Android steps. The exact per-patch cause is unconfirmed. Replay now uses explicit Git committer identity and disables commit signing, backed by a fresh-config replay fixture. Separately, the workflow hydrates and checks LFS files in the replay worktree before screenshot validation. A corrected current-head CI run is pending.

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
