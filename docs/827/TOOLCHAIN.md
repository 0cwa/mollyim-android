# Molly #827 proof of concept toolchain

This record describes the audited source checkout and the Android build inputs used for the patch replay experiment. Update it when a pinned source or build input changes.

## Source pins

| Input | Value |
| --- | --- |
| Signal patch base | `c47a74ba0961903eeaeda6d22347a990056c3e83` |
| Molly comparison target | `0e202dda90785771ff8c87526eaaf30c655f54f3` |
| Audited proof of concept | `b8d5375b3fb6013f7939935ce73e250b53515381` |
| Audited proof of concept tree | `24a27bf3ddf2f23593f5a11e3230b66b335bc2a3` |

## Build versions and dependency inputs

| Input | Pinned value |
| --- | --- |
| Gradle wrapper | 9.4.1 (`gradle/wrapper/gradle-wrapper.properties`) |
| Gradle distribution SHA-256 | `708d2c6ecc97ca9a11838ef64a6c2301151b8dd10387e22dc1a12c30557cab5b` |
| Java toolchain | 21 (`gradle/libs.versions.toml`); CI uses Temurin 21 |
| Android Gradle Plugin | 9.2.1 (`gradle/libs.versions.toml`) |
| Kotlin | 2.2.20 (`gradle/libs.versions.toml`) |
| Compile SDK | Android 36.1 (`gradle/libs.versions.toml`) |
| Android build tools | 36.0.0 (`gradle/libs.versions.toml`) |
| Android NDK | 28.0.13004108 (`gradle/libs.versions.toml`) |
| KtLint | 1.5.0 (`app/build.gradle.kts`) |
| Dependency verification | Strict mode; checksums and signatures in `gradle/verification-metadata.xml` |

Version catalogs under `gradle/` are the dependency version source. The Gradle wrapper verifies the distribution checksum from `gradle/wrapper/gradle-wrapper.properties`; dependency checksums and signatures are checked into `gradle/verification-metadata.xml`. No signing credentials or publishing credentials are part of this workflow.

## Confirmed Gradle task names

The Android application project is named `:Signal-Android` (`settings.gradle.kts` renames the included `:app` project). The selected production flavor task is `:Signal-Android:assemblePlayProdDebug`; this assembles a debug APK without invoking a release signing configuration. The task was confirmed from the generated project task list at `reports/827/build/task-list.txt`.

The branch workflow runs the repository's `ciRemote` task, which includes the app unit tests, fast lint, Kotlin lint, build-logic checks, and screenshot validation, plus the selected Android APK assembly. Gradle dependency verification is explicitly set to strict mode for that invocation.

The validation workflow runs with `--max-workers=1`. `tools/827/test-worker-heap.init.gradle` applies a single 2 GiB test worker after project configuration; the repository default derives parallel test forks from host CPU count and uses a 512 MiB worker, which caused heap exhaustion in MockK/Kotlin metadata during the full staging suite on the local host.

## Baseline evidence and limits

At the start of this run, the evidence in [`reports/827/build/history/attempt20-retry2/`](../../reports/827/build/history/attempt20-retry2/history-index.json) records an ordinary `./gradlew --continue build` attempt at the audited proof-of-concept commit. It started the requested 7,108-task graph, reached 15 of 23 variants and 14 test suites, and stopped with exit 130 after storage reached zero bytes. Thirty test failures were recorded: six each in five package-suffix test variants for `UriUtilTest_isValidExternalUri`. The unsuffixed `testPlayProdDebugUnitTest` suite recorded no failures in the same evidence. The full run is `INCOMPLETE_RESOURCE_EXHAUSTION_INTERRUPTED`, not a passing build.

The historical captured stdout, stderr, exit code, and evidence summary are copied into the repository with original hashes and deterministic gzip copies. The latest F5-focused staging tests passed 25/25 (16 URI suffix cases and 9 UnifiedPush receiver cases); the selected log is `reports/827/build/testPlayStagingDebug-focused-f5-2g-20261024.log`. A full staging suite attempt with the project-default 512 MiB test workers exhausted the test JVM heap in existing `AttachmentBackfillTest` setup; its interrupted log is preserved under `reports/827/build/`. An app ktlint check found an import-order issue in the receiver test, which is being formatted before rerunning lint and the full suite.

These host limitations do not alter the pinned CI toolchain. CI uses a fresh GitHub-hosted runner, installs the declared Android SDK components, and preserves Gradle, replay, test, lint, and APK reports as an artifact. Until that workflow completes successfully, Android build acceptance remains unverified.
