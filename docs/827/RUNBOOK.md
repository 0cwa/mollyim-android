# Replaying and validating the #827 patches

Run the commands below from a checkout of the branch containing `tools/827`.
Use full Git history: the validators inspect pinned commits and provenance, not
just the working tree. For an automated checkout, use `fetch-depth: 0` and fetch
submodules. Git and Python 3.10+ suffice for patch validation; Android checks also
need Git LFS and the [pinned toolchain](TOOLCHAIN.md).

## Check source inputs

```sh
git status --short --branch
git cat-file -e c47a74ba0961903eeaeda6d22347a990056c3e83^{commit}
git cat-file -e 0e202dda90785771ff8c87526eaaf30c655f54f3^{commit}
git cat-file -e d99876269eb6556e37bb2d584ba08e8334e8e5db^{commit}
git merge-base --is-ancestor c47a74ba0961903eeaeda6d22347a990056c3e83 0e202dda90785771ff8c87526eaaf30c655f54f3
```

Fetch missing source objects from Signal's repository for the base and this
repository for the Molly target/application commit. Deepen shallow history when
needed. The validators check the pins, ancestry, and source projection.

## Validate and replay

```sh
python3 tools/827/forest.py check
python3 -m unittest discover -s tools/827 -p 'test_*.py'
python3 tools/827/forest.py verify --repo .
python3 tools/827/validate.py --repo .
python3 tools/827/validate_inventory.py --repo .
python3 tools/827/replay_twice.py --repo . \
  --patches patches/827 --evidence docs/827/parity-evidence.json \
  --worktree-prefix /tmp/molly827 \
  --report reports/827/replay/replay-twice.json
```

Choose an unused worktree prefix. The last command creates
`/tmp/molly827-run-1` and `/tmp/molly827-run-2`, applies the forest independently,
and compares each result with the expected application tree. The explicit
`--repo .` selects this checkout. [PATCH-FOREST.md](PATCH-FOREST.md) describes the
runner's Git isolation and failure behavior; [PARITY.md](PARITY.md) explains what
the assertions establish.

Replay worktrees and per-run logs remain available for inspection and Android
checks. Share generated results through CI artifacts or PR links. Checked-in
inventory ledgers and resource fixtures are validation inputs.

## Prepare Android checks

Install JDK 21, Android platform 36.1, Build Tools 36.0.0, and NDK 28.0.13004108.
Set `JAVA_HOME` and `ANDROID_HOME` to their installation directories, then run:

```sh
"$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" \
  'platform-tools' 'platforms;android-36.1' \
  'build-tools;36.0.0' 'ndk;28.0.13004108'
java -version
./gradlew --version
```

Run Gradle in the reconstructed source worktree. The primary checkout includes
validation fixtures that repository-wide source scanners can otherwise inspect.
Replay skips LFS smudging, so fetch/hydrate and verify its build inputs first:

```sh
PRIMARY_CHECKOUT="$(pwd)"
REPLAY_WORKTREE=/tmp/molly827-run-1
git -C "$REPLAY_WORKTREE" lfs pull
git -C "$REPLAY_WORKTREE" lfs fsck
```

If the required LFS objects are already cached, `git lfs checkout` can hydrate
without downloading them. `fsck` verifies the resulting objects. The Android
application project is named `:Signal-Android`; inspect available tasks with
`./gradlew tasks --all` in the replay worktree.

## Build, test, and lint

The bounded Android workflow runs the repository's `ciRemote` checks and builds
a Play Prod Debug APK with strict dependency verification:

```sh
(cd "$REPLAY_WORKTREE" && ./gradlew --no-daemon --max-workers=1 \
  --dependency-verification=strict \
  --init-script "$PRIMARY_CHECKOUT/tools/827/test-worker-heap.init.gradle" \
  -Dorg.gradle.jvmargs='-Xmx8g -Xms256m -XX:MaxMetaspaceSize=1g -Dcom.android.tools.r8.threadCount=1 -XX:+UnlockExperimentalVMOptions -XX:hashCode=3' \
  ciRemote :Signal-Android:assemblePlayProdDebug)
```

For the URI variant-suffix and UnifiedPush receiver regression tests:

```sh
(cd "$REPLAY_WORKTREE" && ./gradlew --no-daemon --max-workers=1 \
  --dependency-verification=strict \
  --init-script "$PRIMARY_CHECKOUT/tools/827/test-worker-heap.init.gradle" \
  :Signal-Android:testPlayStagingDebugUnitTest \
  --tests org.thoughtcrime.securesms.util.UriUtilTest_isValidExternalUri \
  --tests org.thoughtcrime.securesms.keyvalue.UnifiedPushReceiverAvailabilityTest)
```

Omit the `--tests` filters to run the whole staging suite. Other useful tasks
with the same Gradle settings are `:Signal-Android:ktlintCheck`,
`:fast-lint:fastLint`, and `:Signal-Android:compileWebsiteProdReleaseSources`.
The last compiles release sources without assembling or signing an APK.

The heap init script sets one 2 GiB test worker. The focused example uses
`gradle.properties` for Gradle JVM settings; use the explicit 8 GiB override above
on a smaller host. Add `--offline` only with all dependencies already cached.

### Whole-project build

The full `build` task covers more modules and variants than the bounded CI
command. Quickstart package tasks also require their credential assets through
`quickstart.credentials.dir` in the replay worktree's ignored `local.properties`.
Fixture preparation, historical failures, and the current build scope are tracked
in [issue #4](https://github.com/0cwa/mollyim-android/issues/4). These packaging
inputs are separate from live-service acceptance.

With those inputs prepared, run the full matrix with UTC test JVMs:

```sh
(cd "$REPLAY_WORKTREE" && TZ=UTC ./gradlew --continue --no-daemon \
  --max-workers=1 --dependency-verification=strict \
  --init-script "$PRIMARY_CHECKOUT/tools/827/test-worker-heap.init.gradle" \
  --init-script "$PRIMARY_CHECKOUT/tools/827/test-timezone-utc.init.gradle" \
  -Dorg.gradle.jvmargs='-Xmx8g -Xms256m -XX:MaxMetaspaceSize=1g -Dcom.android.tools.r8.threadCount=1 -XX:+UnlockExperimentalVMOptions -XX:hashCode=3' \
  build)
```

The timezone init script sets `user.timezone=UTC` for Gradle `Test` tasks, making
that setting a test-task input. This makes calendar-dependent tests repeatable
in UTC; it does not replace coverage of application behavior around other zones
or DST transitions. Report failed tasks and fresh versus cached results with the
source revision. A successful app-only task does not establish that the whole
project build passed.

## Conflicts and upgrades

A failed replay retains its worktree and report. Inspect its mailbox, source refs,
owned paths, and upstream API context. Missing history, undeclared dependencies,
and changed context or assertions can cause failure. Retry in a new destination.

For a new upstream version, update the base, feature patches, comparison target,
and application assertions together as described in
[Authoring and upgrading](PATCH-FOREST.md#authoring-and-upgrading). The current
comparison-oracle work is tracked in [issue #3](https://github.com/0cwa/mollyim-android/issues/3).

## Cleanup and further acceptance

After collecting results, remove the disposable replay worktrees. An interrupted
`git am` can be aborted in its worktree before removal. These ordinary Git
commands assume a shell without exported repository-location overrides:

```sh
git worktree remove /tmp/molly827-run-1
git worktree remove /tmp/molly827-run-2
```

If Android outputs leave a worktree dirty, inspect it and use `--force` only when
its remaining contents are disposable. The primary checkout and authored patches
are independent of this cleanup.

Device/service testing and security acceptance are tracked in
[issue #5](https://github.com/0cwa/mollyim-android/issues/5). See
[SECURITY.md](SECURITY.md) for the implementation's trust boundaries. Replay and
local build results alone do not verify live delivery or device privacy behavior.
