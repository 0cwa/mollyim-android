# Signal call-teardown hotfix on Molly's existing native API

The microphone fix is in Signal's **RingRTC native library**, not in the
Signal-Android Java/Kotlin tree. `native-ringrtc.json` pins Molly RingRTC
v2.69.5-1 and Signal commit
`4b1b6fa53c9f30c87c8ea78e44675d4a13e1e4d3`. These helpers cherry-pick that
commit directly into the native source and build it. It is not a mailbox in
the Molly application patchset. The application patchset stays unchanged.

All native production changes and all six regression tests come from Signal.
The only conflict resolution adds the upstream-required test imports while
retaining the older base's `lazy_static`, RNG and `CallManager` imports.
The runner accepts only the two recorded conflicts and their exact Git
stage blobs, then requires the complete reviewed source tree, deterministic
backport commit and production patch ID. Any different conflict fails.

## Source proof without an Android or native toolchain

Run from the application pipeline repository. All output paths below must
be outside the native source. Preparation requires a new source directory.

```sh
python3 tools/native/ringrtc.py prepare \
  --lock native-ringrtc.json \
  --source-dir ../ringrtc-hotfix \
  --proof-dir ../native-proof

python3 tools/native/ringrtc.py verify-source \
  --lock native-ringrtc.json \
  --source-dir ../ringrtc-hotfix \
  --proof-dir ../native-proof

python3 -m unittest discover -s tools/native -p 'test_*.py'
```

The source proof records source identities and patch equality. It does not
assert that a native artifact, Android APK or device call has been tested.

## Native build and application integration

The build uses the original, source-pinned Molly `Dockerfile.android`, runs
the Rust simulation suite with the existing lockfile, and builds release
native libraries for arm, arm64 and x64. It retains Molly's WebRTC fork and
proxy support. This requires Docker, network access, and substantial disk
and build time for WebRTC. A new Maven output directory is required.

```sh
python3 tools/native/ringrtc.py build \
  --lock native-ringrtc.json \
  --source-dir ../ringrtc-hotfix \
  --proof-dir ../native-proof \
  --maven-dir ../native-maven

python3 tools/native/ringrtc.py integrate \
  --lock native-ringrtc.json \
  --app-dir ../reconstructed-molly \
  --maven-dir ../native-maven \
  --proof-dir ../native-proof

python3 tools/native/ringrtc.py verify-integration \
  --lock native-ringrtc.json \
  --app-dir ../reconstructed-molly \
  --maven-dir ../native-maven \
  --proof-dir ../native-proof

cd ../reconstructed-molly
./gradlew --dependency-verification=strict \
  --init-script ../native-proof/ringrtc.init.gradle \
  :app:assembleProdWebsiteDebug
```

The build gives the artifact a distinct local version through the official
`OVERRIDE_VERSION` input. The generated init script substitutes only the
expected historical Molly RingRTC dependency, selects the new version
exclusively from the generated local Maven repository, checks its input
hashes, and rejects disabled dependency verification. It rejects a Signal
artifact or an unexpected RingRTC version instead of silently changing
Molly's native fork.

Integration requires a successful native build/test receipt and rechecks
the artifact hashes, metadata coordinates and all three native ABIs. It
appends checksum entries only for the three locally built AAR/POM/module
files to the reconstructed application's verification metadata. Existing
metadata and trust rules are preserved; no blanket verification exception
or `--write-verification-metadata` operation is added. The original XML is
saved with the proof. Always integrate into a fresh reconstruction.
Before each Gradle invocation, `verify-integration` recomputes that exact
metadata change from the application's committed `HEAD` and checks the
generated init script, verification backup, receipts and artifact hashes.
The application build driver must separately verify its source tree and
index; this helper permits no other working-tree changes.

`commands.log`, `source.json`, `build.json`, `integration.json`, the generated
init script and the verification backup are audit artifacts. A successful
source proof is separate from native test/build success; integration is
separate from Android compilation and device acceptance. Generated native
checksums identify that local build, not an independently reproduced binary
or an official Molly release.

Sources: [upstream fix](https://github.com/signalapp/ringrtc/commit/4b1b6fa53c9f30c87c8ea78e44675d4a13e1e4d3),
[Molly native base](https://github.com/mollyim/ringrtc/tree/8d81a87adcb08b77446b691be3692ff7ed53d580),
[Molly issue #843](https://github.com/mollyim/mollyim-android/issues/843),
[Gradle exclusive repository filters](https://docs.gradle.org/current/userguide/filtering_repository_content.html),
[Gradle dependency verification](https://docs.gradle.org/current/userguide/dependency_verification.html).
