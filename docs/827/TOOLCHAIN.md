# #827 toolchain and inputs

The patch tools need Git and Python 3.10+. Android validation additionally needs
Git LFS, JDK 21, and the SDK/NDK versions selected by this source tree. The
[runbook](RUNBOOK.md) gives setup and validation commands.

## Source identities

| Input | Value |
| --- | --- |
| Signal patch base | `c47a74ba0961903eeaeda6d22347a990056c3e83` |
| Molly comparison target | `0e202dda90785771ff8c87526eaaf30c655f54f3` |
| Expected application commit | `d99876269eb6556e37bb2d584ba08e8334e8e5db` |
| Expected application tree | `e783cf54487a5b5d78c3241ec977fd8c8cd23f1d` |

`patches/827/base` selects the replay base. The separate parity evidence and
validator constants bind the bounded comparison; see [PARITY.md](PARITY.md).
The complete pinned history is needed for ancestry and provenance checks.

## Android build inputs

| Input | Pinned value | Source |
| --- | --- | --- |
| Gradle wrapper | 9.4.1 | `gradle/wrapper/gradle-wrapper.properties` |
| Gradle distribution SHA-256 | `708d2c6ecc97ca9a11838ef64a6c2301151b8dd10387e22dc1a12c30557cab5b` | Wrapper properties |
| Java | 21; CI uses Temurin | `gradle/libs.versions.toml`, `.github/workflows/827-poc.yml` |
| Android Gradle Plugin | 9.2.1 | `gradle/libs.versions.toml` |
| Kotlin | 2.2.20 | `gradle/libs.versions.toml` |
| Compile SDK | Android 36.1 | `gradle/libs.versions.toml` |
| Build Tools | 36.0.0 | `gradle/libs.versions.toml` |
| NDK | 28.0.13004108 | `gradle/libs.versions.toml` |
| KtLint | 1.5.0 | `app/build.gradle.kts` |
| Dependency verification | Strict checksums and signatures | `gradle/verification-metadata.xml` |

The version catalog and wrapper configuration are authoritative build inputs.
The wrapper verifies the Gradle distribution checksum; Android invocations use
`--dependency-verification=strict` for dependency checksums and signatures.
Keep LFS objects hydrated and verified in the reconstructed source worktree
before building.

## Execution settings

The application module is named `:Signal-Android` in `settings.gradle.kts`.
`:Signal-Android:assemblePlayProdDebug` creates a debug APK.
`:Signal-Android:compileWebsiteProdReleaseSources` compiles release sources but
does not assemble or sign a release APK. The retained Signal-derived dependencies
mean that neither task establishes Google-free packaging.

The validation workflow uses `--max-workers=1` and
`tools/827/test-worker-heap.init.gradle`, which sets one 2 GiB JVM for each unit-test
task. The full-build procedure also uses `test-timezone-utc.init.gradle` to set
`user.timezone=UTC` as a Gradle test input. These settings control execution; they
do not change application date logic or substitute for timezone-specific tests.

The workflow's explicit Gradle JVM arguments include the R8 thread-count and
HotSpot hash-code settings used by this proof. Their applicability to the separate
Docker reproducible-build path is tracked in
[issue #2](https://github.com/0cwa/mollyim-android/issues/2). Identical tool versions
and matching source trees alone do not establish identical APKs.
