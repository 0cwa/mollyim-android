# Glide generated-module boundary: current-run decision

**Decision: defer source-level Glide changes for the current pinned Molly827 Phase0–2 proof.** Preserve source pin `D99876269eb6556e37bb2d584ba08e8334e8e5db` and projected tree `e783cf54487a5b5d78c3241ec977fd8c8cd23f1d` as historical evidence. Do not substitute a patched tree or change its identity.

## Terminal build evidence

The public full-root receipt is `reports/827/build/full-root-replay1-20261025/run-receipt.json`. Its recorded fields are `result: FAILED; full-root acceptance not achieved`, `exit.gradle_exit_code: 1`, `exit.build_summary[0]: BUILD FAILED in 5h 34m 44s`, and two entries in `exit.failed_tasks`.

The allowlisted `reports/827/build/full-root-replay1-20261025/task-outcomes.json` records these exact failures:

1. `:demo:image-editor:mergeDexRelease` — “Duplicate class com.bumptech.glide.GeneratedAppGlideModuleImpl during release dex merge.”
2. `:lib:video:verifyReleaseResources` — `video_player.xml:31` references `@color/signal_colorOnSurfaceVariant`, which `lib:video` cannot resolve from its declared dependencies.

The root log is allowlisted at `reports/827/build/all-variant-build-replay1-fixture-utc-input-20261025.log`. Its SHA-256, matching the receipt and task outcomes, is `8b4410ba72bd8ebe66dc8431127cfed81fe6bcbdf13e384b37c75e3439b6ee95`. The public selection is recorded in `reports/827/build/publication-manifest-20261026.json`.

The separate allowlisted `reports/827/build/utc-test-matrix-public-20261026.json` records `projected_repository_tree: e783cf54487a5b5d78c3241ec977fd8c8cd23f1d`, 23 expected and 23 passed variants, and zero failures or errors. The full-root `task-outcomes.json` records 23 app-assembly tasks, all `UP-TO-DATE`. These passing results do not override the terminal full-root failure. A Glide-only fix would also leave the independent video resource failure unresolved.

## Source ownership behind the Glide duplicate

- `lib/glide/build.gradle.kts` applies KSP and the Glide processor. `lib/glide/src/main/java/org/thoughtcrime/securesms/mms/SignalGlideModule.kt` declares `@GlideModule class SignalGlideModule : AppGlideModule`.
- `demo/image-editor/build.gradle` also applies KSP and the Glide processor. `demo/image-editor/src/main/java/org/signal/imageeditor/app/TheAppGlideModule.java` declares its own `@GlideModule class TheAppGlideModule : AppGlideModule`.
- Both processors therefore have an app-module owner that can produce the same `com.bumptech.glide.GeneratedAppGlideModuleImpl` FQCN in the demo's dex inputs. The exact incoming artifacts should be captured if a later isolated investigation is authorized.

## Why disabling demo KSP is unsafe

Removing the demo's KSP processor would leave the library-generated Signal module as the only app-module candidate. That module calls a `lateinit` `RegisterGlideComponents` callback from `registerComponents`. The production app initializes the callback with `SignalGlideComponents`; the camera demo supplies a no-op callback; `ImageEditorApplication` only initializes logging and does not set the callback. A Glide startup through the remaining module could therefore fail. The production callback also registers the `DecryptableUri` loader used by `UriGlideRenderer` when decryptable media is requested. A D8-only pass after disabling KSP would not prove that these paths still work.

## Later source-level follow-up requirements

The optional `:lib:signal-glide` split remains a future recommendation only; it has not been implemented or verified. If a source change is separately authorized:

1. Create a new source baseline and record its actual projected tree. Keep `D99876269eb6556e37bb2d584ba08e8334e8e5db` and `e783cf54487a5b5d78c3241ec977fd8c8cd23f1d` unchanged as historical proof.
2. Re-run the matching 23-patch replay series and all 23 unit suites against that new baseline. Do not carry old-pin results forward.
3. Validate production callback initialization, camera callback initialization, and the image-editor demo's real launch/edit path. Decide and test whether that path needs `DecryptableUri` registration.
4. Independently disposition the `:lib:video:verifyReleaseResources` undeclared-color failure.
5. Re-run all 23 app-variant assemblies, all 23 unit suites, and the unfiltered strict UTC root build. Only a successful root result after both known failure classes are resolved satisfies the full-root build criterion.

The present decision is based on immutable-pin, replay, and behavior-preservation requirements, not implementation effort. No source change or fix claim is made here. The validated case record is in `glide-boundary-case.json`. This directory contains only the sanitized case and summary; it does not include credentials, APKs, or the full build log.
