# Molly patchsets for Signal 8.33.2

This forest reconstructs a **derived development port** of Molly 8.19.2-4 onto
[Signal v8.33.2](https://github.com/signalapp/Signal-Android/releases/tag/v8.33.2).
It contains the complete tracked delta from that Signal release to the pinned
port candidate: **77 mailboxes, 16 feature/review groups, and
3,596 changed paths**, including additions, deletions, resources,
binaries, executable modes, symlinks, build inputs, tests and user documentation.

The official Molly snapshot in [`patches/molly`](../molly/README.md) and the
adapted [`patches/827`](../827/README.md) pilot remain separate. Start this forest
from its own Signal base. The port is not an official Molly release. Current
build results and remaining acceptance work are maintained in
[PR #7](https://github.com/0cwa/mollyim-android/pull/7),
[build issue #4](https://github.com/0cwa/mollyim-android/issues/4), and
[device issue #5](https://github.com/0cwa/mollyim-android/issues/5).

## Source pins

| Input | Commit or tree |
| --- | --- |
| Signal v8.33.2 (`base`) | `6e9dddc01f1b26e608ac683807c51e139c141ed2` |
| Original Signal 8.19.2 (`origin-base`) | `c47a74ba0961903eeaeda6d22347a990056c3e83` |
| Official Molly 8.19.2-4 (`origin-target`) | `0e202dda90785771ff8c87526eaaf30c655f54f3` |
| Derived Signal merge (`upstream-merge`) | `90a0bb917ecc49a62236d539f4e7faae01b1d9fe` |
| Derived candidate (`target`) | `1dc39842dfad7c31be516556f8da95556d6c810f` |
| Complete candidate tree | `48776ef81992b2b2c5418d8d55d9113094fe9124` |

The [source merge](https://github.com/0cwa/mollyim-android/commit/90a0bb917ecc49a62236d539f4e7faae01b1d9fe)
has the original Molly target as its first parent and Signal v8.33.2 as its
second parent. The [candidate](https://github.com/0cwa/mollyim-android/commit/1dc39842dfad7c31be516556f8da95556d6c810f)
includes the subsequent reviewed integration fix. Source history is available
on `port/molly-signal-8.33.2`; the immutable pin files determine what is replayed,
even when that branch later advances.

## Feature patchsets and changed code

Each feature directory has one `series`. Its mailboxes separate unchanged
carryovers from adaptations, with names such as `0001-carryover.patch` and
`0002-adapted.patch`. Larger batches continue the numbering. There are
**38 carryover mailboxes covering 1,881 paths** and **39 adapted mailboxes
covering 1,715 paths**.

| Feature/review group | Carryover paths | Adapted paths | Mailboxes |
| --- | ---: | ---: | ---: |
| `app-updates` | 5 | 7 | 2 |
| `appearance` | 16 | 12 | 2 |
| `backup-and-restore` | 4 | 24 | 2 |
| `documentation` | 7 | 0 | 1 |
| `google-services` | 81 | 0 | 1 |
| `maps` | 14 | 1 | 2 |
| `module-pruning` | 496 | 521 | 15 |
| `networking-and-proxies` | 22 | 17 | 2 |
| `notifications-and-unifiedpush` | 24 | 17 | 2 |
| `payments-and-donations` | 220 | 41 | 4 |
| `privacy-controls` | 7 | 8 | 2 |
| `registration-and-linking` | 12 | 134 | 3 |
| `resources-and-branding` | 691 | 519 | 29 |
| `security-and-locking` | 27 | 8 | 2 |
| `integration` | 173 | 371 | 6 |
| `build-and-release` | 82 | 35 | 2 |

A path is a **carryover** only when both of these are true:

- Its entry in Signal 8.33.2 is identical to its entry in the original Signal base.
- Its entry in the port is identical to its entry in the original Molly target.

An entry includes mode, object type, object ID and absence. Every other exported
path is **adapted**, including moved code, new compatibility work and new files
under removed modules. A path equal to Signal 8.33.2 needs no patch. The verifier
checks these labels against all four trees; filenames alone are not evidence.

Whole files remain together, and each changed path belongs to exactly one
mailbox and one group. Shared application and library integration remains in
`integration`. These groups organize review and maintenance; the complete
forest is the supported reconstruction. They do not promise independently
buildable or optional features. Unchanged file bytes can still interact with
changed callers, dependencies and runtime behavior.

Every mailbox identifies the derived target with `Source-Commit`, and records
`Origin-Base`, `Origin-Target` and `Port-Category`. The mailbox `From` commit is a
reconstruction export, not an original upstream feature commit. Existing source
attribution and license headers remain intact.

## Inspect and reconstruct

Use Git and Python 3.10+. Run from a repository containing this forest and the
pinned history. Fetch the source branch when needed:

```sh
git fetch --no-tags https://github.com/0cwa/mollyim-android.git \
  refs/heads/port/molly-signal-8.33.2
python3 tools/827/forest.py check --patches patches/molly-signal-8.33.2
python3 tools/827/forest.py series --patches patches/molly-signal-8.33.2
python3 tools/827/verify_complete.py --repo . \
  --patches patches/molly-signal-8.33.2
```

To retain the reconstructed source for a build, choose a new path outside the
checkout:

```sh
python3 tools/827/verify_complete.py --repo . \
  --patches patches/molly-signal-8.33.2 \
  --worktree /tmp/molly-signal-port \
  --report /tmp/molly-signal-port-verification.json
```

Verification checks provenance and ancestry, actual applied path ownership,
complete delta coverage and carryover/adapted classification. It applies two
legal full orders and requires both complete Git trees to equal the pinned
candidate, **without path or metadata exclusions**. It also requires clean
indexes and working files, with no untracked or ignored extras.

The candidate preserves some inherited source whitespace. `verify_complete.py`
reports it and accepts it only after exact target-tree equality. Use this
complete verifier for reconstruction; the generic forest CLI keeps its strict
whitespace policy. No command silently rewrites the source to satisfy a check.

## Build and focused tests

Install **JDK 21**, and these Android SDK packages:

```sh
sdkmanager --install 'platforms;android-37.0' 'build-tools;36.0.0' \
  'ndk;28.0.13004108'
```

From the verified source directory, use its checked-in **Gradle 9.6** wrapper:

```sh
cd /tmp/molly-signal-port
./gradlew --no-daemon --dependency-verification=strict \
  :app:assembleProdWebsiteDebug
```

This builds the Website debug variant. The candidate's version includes
`port-unvalidated`; no CI release property is needed. Molly's corresponding
native forks are pinned to libsignal **0.105.4-1** and RingRTC **2.73.0-1**, with
published artifact checksums in dependency-verification metadata.

The [dedicated workflow](../../.github/workflows/molly-signal-port.yml) performs
the same exact reconstruction and build, then runs focused proxy, registration,
encrypted-preference migration, backup, notification, connectivity and settings
tests. It preserves strict dependency verification, bounds worker memory and
uploads the APK, source proof, test reports and failure logs as CI artifacts.
Build status belongs in the linked PR and issues, rather than checked-in run logs.

Source equality proves coverage of the pinned derived candidate. A debug build
and focused tests are additional gates; device behavior, live delivery, linking,
lock semantics, APK reproducibility and release acceptance require their own
validation.

## Review impact and regenerate

Before changing the port, inspect which original Molly paths overlap a proposed
upstream base:

```sh
python3 tools/827/port_impact.py --repo . --source-forest patches/molly \
  --base 6e9dddc01f1b26e608ac683807c51e139c141ed2 \
  --report /tmp/molly-upstream-impact.json
```

This read-only comparison reports unchanged bases, already-upstream changes,
changed bases and new files under entirely removed module scopes. It does not
assert that a clean patch applies or that an unchanged file will compile.

Regenerate into a new output directory, retaining the reviewed source pins:

```sh
python3 tools/827/export_complete.py --repo . \
  --base "$(cat patches/molly-signal-8.33.2/base)" \
  --target "$(cat patches/molly-signal-8.33.2/target)" \
  --upstream-merge "$(cat patches/molly-signal-8.33.2/upstream-merge)" \
  --origin-base "$(cat patches/molly-signal-8.33.2/origin-base)" \
  --origin-target "$(cat patches/molly-signal-8.33.2/origin-target)" \
  --output /tmp/molly-signal-port-export
python3 tools/827/verify_complete.py --repo . \
  --patches /tmp/molly-signal-port-export
```

The exporter derives whole-file groups, uses a private index and fixed export
identity, and takes the target commit's timestamp. It refuses an existing output
directory. The README and mailbox whitespace attributes are maintained alongside
the generated pins, mailboxes and series files. See the
[maintenance guide](../../docs/827/PATCH-FOREST.md) for the shared format and Git
safeguards, and [scope guide](../../docs/827/PARITY.md) for the distinct proofs.
