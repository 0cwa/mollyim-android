# Molly #827 patch replay runbook

This runbook applies to the review branch `dev/molly-827-reproducible-poc` after it is available on the Molly repository. Clone the branch at full history depth (the default `git clone` is not shallow), including submodules:

```sh
git clone --branch dev/molly-827-reproducible-poc --recurse-submodules \
  https://github.com/0cwa/mollyim-android.git molly-827-reproducible-poc
cd molly-827-reproducible-poc
```

If using an automated checkout action, set `fetch-depth: 0` and enable recursive submodules. Use a disposable checkout with enough disk space; the full Android build writes substantial temporary and APK output.

## Toolchain

The recorded environment used Gradle wrapper 9.4.1, JDK 21, Kotlin 2.2.20, Android Gradle Plugin 9.2.1, Android SDK API 36.1, Build Tools 36.0.0, and NDK 28.0.13004108. Install JDK 21 (for example, `openjdk-21-jdk` on Ubuntu), then install the Android packages through the SDK Manager. The wrapper pins Gradle; the project selects the matching SDK and NDK. For API 36 / Build Tools 36.0.0 / NDK 28.0.13004108, the command is:

```sh
sdkmanager "platform-tools" "platforms;android-36" \
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

The explicit `--repo .` is important: it uses this candidate checkout, not the checkout’s `origin` remote (which may point to a local source mirror). A PASS means both independent patch applications produced identical Git trees and the declared ownership checks passed. It does not establish application behavior or a successful Android build. The per-run JSON and logs are in the same report directory. After preserving evidence, remove only the replay worktrees:

```sh
git worktree remove --force /tmp/molly827-run-1
git worktree remove --force /tmp/molly827-run-2
```

## Android build and tests

For a regular local check, inspect actual tasks in this checkout with `./gradlew tasks --all`, then use the relevant unit test or assemble task. The branch workflow's bounded CI build, test, lint, strict dependency verification, and production debug APK tasks are:

```sh
./gradlew --no-daemon --max-workers=2 --dependency-verification=strict \
  -Dorg.gradle.jvmargs='-Xmx8g -Xms256m -XX:MaxMetaspaceSize=1g -Dcom.android.tools.r8.threadCount=1 -XX:+UnlockExperimentalVMOptions -XX:hashCode=3' \
  ciRemote :Signal-Android:assemblePlayProdDebug
```

The focused flavor-suffix and receiver regression tasks are:

```sh
./gradlew --no-daemon --max-workers=2 --dependency-verification=strict \
  -Dorg.gradle.jvmargs='-Xmx8g -Xms256m -XX:MaxMetaspaceSize=1g -Dcom.android.tools.r8.threadCount=1 -XX:+UnlockExperimentalVMOptions -XX:hashCode=3' \
  :Signal-Android:testPlayStagingDebugUnitTest \
  --tests org.thoughtcrime.securesms.util.UriUtilTest_isValidExternalUri \
  --tests org.thoughtcrime.securesms.keyvalue.UnifiedPushReceiverAvailabilityTest
```

The recorded full-build run used a single worker and bounded R8/worker settings. Its init scripts live in `/workspace/work/p2-baseline` and are specific to that evidence environment:

```sh
./gradlew --no-daemon --max-workers=1 --continue \
  -I /workspace/work/p2-baseline/test-worker-heap.init.gradle \
  -I /workspace/work/p2-baseline/attempt20-retry2-capacity-ordering.init.gradle \
  -Dorg.gradle.jvmargs='-Xmx8g -Xms256m -XX:MaxMetaspaceSize=1g -Dcom.android.tools.r8.threadCount=2 -XX:+UnlockExperimentalVMOptions -XX:hashCode=3 -XX:ActiveProcessorCount=4' \
  build
```

That run was interrupted by disk exhaustion (exit 130). The matrix reached 15 of 23 variants and 14 test suites before the filesystem reached zero free space. Thirty failures were attributed to `UriUtilTest_isValidExternalUri` fixture assumptions across package-suffix variants; that fixture has since been adapted. The full build was on the audited base before the latest patch set, so rerun CI against the current head. The exact build evidence is in `reports/827/build/` and `/workspace/work/p2-baseline/attempt20-retry2-build-evidence-summary.json`. The latest focused production unit task also failed at test compilation because `UnifiedPushReceiverAvailabilityTest.kt` referenced unresolved MockK `anyConstructed`; see `reports/827/build/testPlayProdDebugUnitTest.log`. The latest frozen staging-focused run is in progress at `:Signal-Android:compilePlayStagingDebugKotlin`; its current log and source snapshot are `reports/827/build/testPlayStagingDebug-focused-frozen-20261024.log` and `reports/827/build/focused-source-snapshot-20261024.json`. A focused successful task cannot turn an incomplete full build into a pass.

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
