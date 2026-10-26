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

### Full all-variant build and test timezone

Run the full `build` task from the replay worktree with both reviewed init scripts. `TZ=UTC` sets the Gradle process timezone, and `test-timezone-utc.init.gradle` also configures every Gradle `Test` task with `user.timezone=UTC`. Gradle treats test system properties as task inputs, so the timezone value participates in the test task cache key and avoids reusing results produced under a different timezone. The timezone script changes only test JVM configuration; it does not change application date handling or add a test filter.

```sh
(cd "$REPLAY_WORKTREE" && TZ=UTC ./gradlew --continue --no-daemon --max-workers=1 --dependency-verification=strict \
  --init-script "$PRIMARY_CHECKOUT/tools/827/test-worker-heap.init.gradle" \
  --init-script "$PRIMARY_CHECKOUT/tools/827/test-timezone-utc.init.gradle" \
  -Dorg.gradle.jvmargs='-Xmx8g -Xms256m -XX:MaxMetaspaceSize=1g -Dcom.android.tools.r8.threadCount=1 -XX:+UnlockExperimentalVMOptions -XX:hashCode=3' \
  build)
```

A `CollapsingMessagesTests` case uses `now() - 24h` while `DateUtils.isSameDay` compares local calendar dates. On the 25-hour Europe/Stockholm DST transition day, an elapsed 24-hour interval can still be the same local date, so a calendar-dependent `HEAD` expectation can disagree with the actual `PENDING` result. The source date comparison is intentionally unchanged; use UTC for deterministic unit-test execution and retain timezone/DST-specific coverage for the underlying date behavior. The sanitized [public prior-attempt summary](../../reports/827/build/local-reconstruction-20261025/prior-attempts-summary.json) records the DST investigation and UTC configuration. The completed current-source full build exited 1 after 5h 34m 44s; Gradle reports 4,938 actionable tasks (1,858 executed, 301 from cache, 2,779 up-to-date). It failed at `:demo:image-editor:mergeDexRelease` (duplicate `GeneratedAppGlideModuleImpl`) and `:lib:video:verifyReleaseResources` (unresolved `color/signal_colorOnSurfaceVariant` at `video_player.xml:32`). The video build file and layout are unchanged from the pinned Signal base; the layout uses a color defined by `core:ui`, but `lib:video` does not declare that dependency. The public [run receipt](../../reports/827/build/full-root-replay1-20261025/run-receipt.json) and [task outcomes](../../reports/827/build/full-root-replay1-20261025/task-outcomes.json) accompany the linked [replay 1 log](../../reports/827/build/all-variant-build-replay1-fixture-utc-input-20261025.log). A later app-only `:Signal-Android:build` diagnostic exited 0, but all 23 app assemble and unit-test tasks were up-to-date, so it did not produce fresh tests and does not change the failed full-matrix result; see the public [app-only receipt](../../reports/827/build/app-only-signal-android-build-replay1-20261026/public-run-receipt.json) and its allowlisted [build log](../../reports/827/build/app-only-signal-android-build-replay1-20261026/build.log) (log SHA-256 `842f5b05246123bcb5c04e6d445e9b2f24220be5f202fbc284ca99144b718bde`). Do not treat the matrix as passed.

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

### Current-source API35 synthetic runtime probe

The current-source benchmark APK was also exercised on a fresh API35 x86_64 Google APIs emulator. The bounded seed and process-restart phases passed for synthetic account setup, selected UnifiedPush preference/backup checks, clipboard payloads and sensitive metadata, fake distributor callbacks, synthetic connector-token persistence across app process restart, unregister cleanup, and the missing-VAPID WebSocket-availability transition. This run does not validate a live Signal account, MollySocket, real distributor, physical device, locked notification presentation, API35 clipboard expiry, or cryptographic lock semantics. It does not replace the all-variant matrix, which completed with two failures described above.

The full text-only runner source, API30-to-API35 diff, source pins, checksums, captured logs, failed-attempt dispositions, and exact invocation are in [the API35 runtime report](../../reports/827/security/runtime/api35-20261025/README.md). Use a fresh API35 Google APIs x86_64 AVD with `-wipe-data`; the run script requires emulator root, sets airplane mode and requests Wi-Fi/mobile radio disablement, installs the no-INTERNET fake distributor, and requires exact IPv4 and IPv6 guest OUTPUT DROP rules before instrumentation. Build `:Signal-Android:assemblePlayProdBenchmark` from the replayed source worktree, sign the separate instrumentation runner with the same local debug keystore, and verify the certificate match as documented in the harness. The run script clears only the disposable benchmark app's data, runs seed and restart, verifies PASS markers, and removes the fake distributor. Shut down the AVD after evidence capture. The recorded API35 run is synthetic, local-only evidence; it does not prove a real notification display or a remote delivery path.

### Inputs for a bounded live probe

No live Signal, MollySocket, or real-distributor probe has been run. The API35 result above is synthetic and offline. The following inputs and capabilities are needed before a future live probe can be executed:

* Use a disposable nonproduction Signal identity already registered on Signal. Its account holder needs to make the primary device available to scan and approve the linked-device QR. Record the artifact variant and its compiled `BuildConfig.SIGNAL_URL`: this build sets the Play Prod base in `app/build.gradle.kts:250` and the Staging base in `app/build.gradle.kts:473`; the selected variant determines the service configuration. The authorized test must not use a variant resolving to production. The server revision and image digest are unknown unless independently supplied; the client does not provide an arbitrary Signal URL input.
* Provide a test MollySocket web-server URL and its matching link QR. The parser accepts `mollysocket://link` with `type=webserver`, an 87-character `vapid` value, and an HTTPS `url` (`app/src/main/java/im/molly/unifiedpush/model/MollySocket.kt:10-33`). The client performs GET discovery and then POST registration to that same URL without following redirects (`app/src/main/java/im/molly/unifiedpush/MollySocketRepository.kt:152-210`). The POST JSON fields are `uuid`, `device_id`, `password`, `endpoint`, and `ping` (`app/src/main/java/im/molly/unifiedpush/model/ConnectionRequest.kt:5-11`); record the returned `mollysocket.version` and status (`app/src/main/java/im/molly/unifiedpush/model/ConnectionRequest.kt:13-29`). No server URL, route suffix, deployed version, or deployment digest is supplied here, and this client contract does not establish a compatible server release.
* Provide an installed UnifiedPush distributor that acknowledges the app and can return an endpoint for the link's VAPID value. Record its package/version and the registration/endpoint events relevant to each scenario. Receiver actions include endpoint, registration-failure, unregistered, and message callbacks (`app/src/main/java/im/molly/unifiedpush/receiver/UnifiedPushReceiver.kt:37-85`). Treat these as scenario-specific observations: app-initiated `unregisterApp()` clears the stored endpoint and does not itself invoke `onUnregistered` (`app/src/main/java/im/molly/unifiedpush/UnifiedPushDistributor.kt:17-22`).
* Use an API 33 or later device or emulator for the clipboard-sensitive-metadata scenario. Record Android API/build, ABI, APK package/version/SHA-256 and signer, app lock state, OS keyguard state, notification permission, and distributor package/version. The API35 run only verified sensitive clipboard metadata; rendered Settings UI, clipboard expiry, locked notification presentation, and cryptographic lock behavior remain unverified. Keep app lock and OS keyguard state as separate observations (`app/src/main/java/im/molly/unifiedpush/receiver/UnifiedPushReceiver.kt:34-35`; notification permission is declared in `app/src/main/AndroidManifest.xml:50`).
* Keep the primary account available to list and remove any linked device created by the probe. This also permits cleanup if provisioning stops after the Signal device is created but before MollySocket registration completes. Test an unsolicited `UNREGISTERED` callback only if that callback scenario is in scope; normal app-initiated unregister is not evidence of that callback.

Record UTC start/end, network route or proxy, request method and outcome, response status/version, whether redirects occurred, selected build configuration, OS/app/distributor identities, callback sequence, and cleanup result. These are evidence fields, not additional approval gates. Redact phone numbers, account/device identifiers, QR contents, verification codes, passwords, push endpoints, VAPID values, and message bodies from retained evidence. Current environment does not include a disposable live identity, MollySocket deployment, or real distributor; their URLs, versions, digests, and device values remain missing rather than inferred.

### Quickstart packaging inputs for the full variant build

For a fresh full-matrix run, first build the benchmark APK needed by the offline fixture exporter, then generate/validate the private package-only fixture, set `quickstart.credentials.dir`, and only then run the full matrix. The bounded prerequisite is `:Signal-Android:assemblePlayProdBenchmark`; it does not depend on Quickstart credentials. Follow the [synthetic fixture-generation record](../../reports/827/build-environment/quickstart-20261025/README.md): it uses the canonical `QuickstartCredentialExporter` with locally generated benchmark `TestUsers` data on an isolated API 35 emulator. The evidence bundle includes the temporary exporter harness, schema validator, setup and cleanup records, and exact source/APK identities. Do not start another full `build` before the private fixture is ready.

Keep the generated JSON files in a private directory outside the checkout (directory mode 700, files mode 600); the JSON contains synthetic account credentials and serialized keys. The recorded package-only inputs are `prod_synthetic.json` and `staging_synthetic.json`, copied from the same local synthetic export to meet the two flavor filename prefixes. Never commit the fixture JSON, generated account values, or keys. In the **isolated replay worktree** used for the full build, set the ignored root `local.properties` entry to the private directory:

```properties
quickstart.credentials.dir=/path/to/private/quickstart-fixtures
```

Resume the full build from that replay worktree after the original `--continue` run has finished. This property only supplies assets to the Quickstart package tasks. Do not install or launch a Quickstart APK. Fixture generation and schema/base64 validation do not prove Quickstart deserialization, registration, protocol or cryptographic correctness, or live Signal/MollySocket behavior. The benchmark TestUsers setup has a documented PNI prekey-generation concern; this packaging fixture does not fix or validate it.

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
