"""Fail-closed source and artifact boundaries for the native backport runner."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import ringrtc


LOCK = ringrtc.read_lock(Path(__file__).resolve().parents[2] / "native-ringrtc.json")
METADATA = '''<?xml version="1.0" encoding="UTF-8"?>
<verification-metadata xmlns="https://schema.gradle.org/dependency-verification">
   <configuration>
      <verify-metadata>true</verify-metadata>
      <trusted-artifacts><trust file=".*[.]pom" regex="true"/></trusted-artifacts>
   </configuration>
   <components>
      <component group="existing" name="dependency" version="1"><artifact name="dep.jar"><sha256 value="old"/></artifact></component>
   </components>
</verification-metadata>
'''


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self.temporary.cleanup)

    def artifacts(self):
        directory = self.root / "maven" / "im/molly/ringrtc-android" / LOCK["artifact_version"]
        directory.mkdir(parents=True)
        stem = "ringrtc-android-" + LOCK["artifact_version"]
        aar = directory / (stem + ".aar")
        with zipfile.ZipFile(aar, "w") as archive:
            archive.writestr("classes.jar", b"fixture")
            for abi in ("armeabi-v7a", "arm64-v8a", "x86_64"):
                for library in ("libringrtc.so", "libringrtc_rffi.so"):
                    archive.writestr(f"jni/{abi}/{library}", b"fixture")
        (directory / (stem + ".pom")).write_text(
            f'<project xmlns="http://maven.apache.org/POM/4.0.0"><groupId>im.molly</groupId>'
            f'<artifactId>ringrtc-android</artifactId><version>{LOCK["artifact_version"]}</version></project>')
        (directory / (stem + ".module")).write_text(json.dumps({
            "component": {"group": "im.molly", "module": "ringrtc-android", "version": LOCK["artifact_version"],
                          "attributes": {"org.gradle.status": "release"}},
            "variants": [{"files": [{"name": aar.name, "url": aar.name, "sha256": ringrtc.sha256(aar)}]}],
        }))
        return self.root / "maven", directory, stem

    def test_only_known_import_conflicts_are_resolved(self):
        conflict = lambda ours, theirs: f"<<<<<<< HEAD\n{ours}=======\n{theirs}>>>>>>> source\n"
        text = "prefix\n" + conflict("", ringrtc.FIRST_THEIRS) + "middle\n" + conflict(ringrtc.SECOND_OURS, ringrtc.SECOND_THEIRS) + "suffix\n"
        result = ringrtc.resolve_test_imports(text)
        self.assertIn("sync::{Arc, Condvar, Mutex}", result)
        self.assertIn("ConnectionObserverEvent", result)
        self.assertNotIn("LazyLock", result)
        self.assertNotIn("CreateGroupCallParams", result)
        self.assertTrue(result.endswith("suffix\n"))
        with self.assertRaises(ringrtc.Failure):
            ringrtc.resolve_test_imports(text.replace("LazyLock", "UnexpectedType"))
        with self.assertRaises(ringrtc.Failure):
            ringrtc.resolve_test_imports(text + conflict("new\n", "other\n"))

    def test_known_repo_allowlist_and_distinct_version(self):
        for key, value in (("base_repository", "https://example.com/ringrtc.git"),
                           ("artifact_version", LOCK["original_version"])):
            candidate = copy.deepcopy(LOCK)
            candidate[key] = value
            path = self.root / "bad-lock.json"
            path.write_text(json.dumps(candidate))
            with self.assertRaises(ringrtc.Failure):
                ringrtc.read_lock(path)

    def test_verification_append_preserves_existing_bytes(self):
        hashes = {"ringrtc.aar": "a" * 64, "ringrtc.module": "b" * 64, "ringrtc.pom": "c" * 64}
        updated = ringrtc.extend_verification(METADATA, LOCK, hashes)
        prefix, suffix = METADATA.split("   </components>")
        self.assertTrue(updated.startswith(prefix))
        self.assertTrue(updated.endswith("   </components>" + suffix))
        self.assertNotIn("trusted-key", updated)
        self.assertEqual(updated.count("<trust "), METADATA.count("<trust "))
        with self.assertRaises(ringrtc.Failure):
            ringrtc.extend_verification(updated, LOCK, hashes)

    def test_verification_rejects_disabled_metadata_and_trusted_aar(self):
        for unsafe in (METADATA.replace("true</verify-metadata>", "false</verify-metadata>"),
                       METADATA.replace(".*[.]pom", ".*[.]aar")):
            with self.assertRaises(ringrtc.Failure):
                ringrtc.extend_verification(unsafe, LOCK, {"ringrtc.aar": "a" * 64})

    def test_artifact_requires_all_metadata_and_all_abis(self):
        maven, directory, stem = self.artifacts()
        self.assertEqual(len(ringrtc.artifact_files(LOCK, maven)), 3)
        (directory / (stem + ".module")).unlink()
        with self.assertRaises(ringrtc.Failure):
            ringrtc.artifact_files(LOCK, maven)

    def test_artifact_rejects_changed_bytes_and_module_path_escape(self):
        maven, directory, stem = self.artifacts()
        aar = directory / (stem + ".aar")
        with aar.open("ab") as target:
            target.write(b"changed")
        with self.assertRaises(ringrtc.Failure):
            ringrtc.artifact_files(LOCK, maven)
        module = directory / (stem + ".module")
        content = json.loads(module.read_text())
        content["variants"][0]["files"][0]["url"] = "../../other.aar"
        module.write_text(json.dumps(content))
        with self.assertRaises(ringrtc.Failure):
            ringrtc.artifact_files(LOCK, maven)

    def test_integrate_requires_successful_build_and_rechecks_hashes(self):
        maven, directory, stem = self.artifacts()
        proof = self.root / "proof"
        runner = ringrtc.Runner(proof, LOCK)
        app = self.root / "app"
        (app / "gradle").mkdir(parents=True)
        metadata = app / "gradle/verification-metadata.xml"
        metadata.write_text(METADATA)
        with self.assertRaises(ringrtc.Failure):
            ringrtc.integrate(runner, app, maven)
        files = ringrtc.artifact_files(LOCK, maven)
        receipt = {"status": "passed", "simulation_tests": "passed", "source_commit": LOCK["source_commit"],
                   "source_tree": LOCK["source_tree"], "artifact_version": LOCK["artifact_version"],
                   "artifacts": {name: ringrtc.sha256(path) for name, path in files.items()}}
        ringrtc.write_json(proof / "build.json", receipt)
        receipt["artifacts"][stem + ".aar"] = "0" * 64
        ringrtc.write_json(proof / "build.json", receipt)
        with self.assertRaises(ringrtc.Failure):
            ringrtc.integrate(runner, app, maven)
        self.assertEqual(metadata.read_text(), METADATA)

    def test_source_verifier_rejects_changed_tree_before_recording_success(self):
        class UnexpectedTree:
            lock = LOCK
            proof = self.root / "proof"

            def value(self, source, *args):
                if args == ("rev-parse", "--show-toplevel"):
                    return str(source)
                if args == ("rev-parse", "HEAD"):
                    return LOCK["source_commit"]
                return "0" * 40

        with self.assertRaises(ringrtc.Failure):
            ringrtc.verify_source(UnexpectedTree(), self.root)
        self.assertFalse((self.root / "proof/source.json").exists())

    def test_integration_verifier_recomputes_head_transform_and_init(self):
        maven, directory, stem = self.artifacts()
        proof = self.root / "proof"
        runner = ringrtc.Runner(proof, LOCK)
        app = self.root / "app"
        (app / "gradle").mkdir(parents=True)
        metadata = app / "gradle/verification-metadata.xml"
        metadata.write_text(METADATA)
        runner.git(app, "init", "--template=")
        runner.git(app, "add", ".")
        runner.git(app, "commit", "-m", "Original fixture verification metadata")
        files = ringrtc.artifact_files(LOCK, maven)
        ringrtc.write_json(proof / "build.json", {"status": "passed", "simulation_tests": "passed",
            "source_commit": LOCK["source_commit"], "source_tree": LOCK["source_tree"],
            "artifact_version": LOCK["artifact_version"], "artifacts": {name: ringrtc.sha256(path) for name, path in files.items()}})
        ringrtc.integrate(runner, app, maven)
        verified = ringrtc.verify_integration(runner, app, maven)
        self.assertEqual(verified["verification_sha256"], ringrtc.sha256(metadata))
        init = proof / "ringrtc.init.gradle"
        original_init = init.read_bytes()
        init.write_bytes(original_init + b"\n// unexpected edit\n")
        with self.assertRaises(ringrtc.Failure):
            ringrtc.verify_integration(runner, app, maven)
        init.write_bytes(original_init)
        metadata.write_text(metadata.read_text() + "\n")
        with self.assertRaises(ringrtc.Failure):
            ringrtc.verify_integration(runner, app, maven)


if __name__ == "__main__":
    unittest.main()
