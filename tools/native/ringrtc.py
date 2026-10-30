#!/usr/bin/env python3
"""Reconstruct Signal's native hotfix; build and consume an isolated Molly AAR."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile


class Failure(RuntimeError):
    pass


HERE = Path(__file__).resolve().parent
NS = "https://schema.gradle.org/dependency-verification"
IMPORT_PATH = "src/rust/tests/common/mod.rs"
GIT_OPTIONS = [
    "-c", "user.name=Patch Pipeline", "-c", "user.email=patch-pipeline@localhost",
    "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
    "-c", "rerere.enabled=false", "-c", "core.autocrlf=false",
    "-c", "merge.conflictStyle=merge", "-c", "core.abbrev=7",
]
FIRST_THEIRS = "    sync::{Arc, Condvar, LazyLock, Mutex},\n"
SECOND_OURS = (
    "    common::{ApplicationEvent, CallEndReason, CallMediaType, DeviceId},\n"
    "    core::{call::Call, call_manager::CallManager, connection::Connection, group_call, signaling},\n"
)
SECOND_THEIRS = """    common::{
        ApplicationEvent, CallEndReason, CallMediaType, DataMode, DeviceId, EVENT_QUEUE_SIZE,
    },
    core::{
        call::Call,
        call_manager::{CallManager, CreateGroupCallParams},
        connection::{Connection, ConnectionObserverEvent},
        group_call, signaling,
    },
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def read_lock(path: Path) -> dict:
    lock = json.loads(path.read_text())
    require(lock["schema"] == 1, "Unsupported native lock schema")
    require(lock["base_repository"] == "https://github.com/mollyim/ringrtc.git", "Unexpected Molly repository")
    require(lock["upstream_repository"] == "https://github.com/signalapp/ringrtc.git", "Unexpected Signal repository")
    for name in ("base_commit", "upstream_commit", "source_commit", "source_tree", "production_patch_id"):
        require(re.fullmatch(r"[0-9a-f]{40}", lock[name]) is not None, f"Invalid {name}")
    require(lock["artifact_group"] == "im.molly" and lock["artifact_name"] == "ringrtc-android", "Unexpected native coordinate")
    for name in ("artifact_version", "original_version"):
        require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]+", lock[name]) is not None, f"Invalid {name}")
    require(lock["artifact_version"] != lock["original_version"], "Hotfix must have a distinct artifact version")
    require(lock["test_import_resolution"]["path"] == IMPORT_PATH, "Unexpected conflict resolution path")
    return lock


def git_environment(lock: dict | None = None) -> dict:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("GIT_CONFIG_", "GIT_AUTHOR_", "GIT_COMMITTER_")) or key in {
            "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
            "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG",
            "GIT_ATTR_SOURCE", "GIT_EXTERNAL_DIFF", "GIT_DIFF_OPTS", "GIT_TEMPLATE_DIR",
        }:
            del env[key]
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0", GIT_ATTR_NOSYSTEM="1", GIT_NO_REPLACE_OBJECTS="1")
    if lock:
        env["GIT_COMMITTER_DATE"] = lock["commit_date"]
    return env


class Runner:
    def __init__(self, proof: Path, lock: dict):
        proof.mkdir(parents=True, exist_ok=True)
        self.proof, self.lock = proof, lock

    def run(self, args: list[str], *, cwd: Path | None = None, data: bytes | None = None,
            check: bool = True, stream: bool = False) -> subprocess.CompletedProcess:
        with (self.proof / "commands.log").open("ab") as log:
            log.write((json.dumps(args) + "\n").encode())
            log.flush()
            result = subprocess.run(args, cwd=cwd, input=data, env=git_environment(self.lock),
                                    stdout=log if stream else subprocess.PIPE, stderr=subprocess.STDOUT)
            if not stream:
                log.write(result.stdout)
            require(not check or result.returncode == 0,
                    f"Command failed ({result.returncode}); see {self.proof / 'commands.log'}")
            return result

    def git(self, source: Path, *args: str, check: bool = True, data: bytes | None = None) -> subprocess.CompletedProcess:
        return self.run(["git", *GIT_OPTIONS, "-C", str(source), *args], check=check, data=data)

    def value(self, source: Path, *args: str) -> str:
        return self.git(source, *args).stdout.decode().strip()


def resolve_test_imports(text: str) -> str:
    """Accept only the two observed import conflicts, never arbitrary resolutions."""
    pattern = re.compile(r"^<<<<<<<[^\n]*\n(.*?)^=======\n(.*?)^>>>>>>>[^\n]*\n", re.M | re.S)
    matches = list(pattern.finditer(text))
    expected = [("", FIRST_THEIRS), (SECOND_OURS, SECOND_THEIRS)]
    require([m.groups() for m in matches] == expected, "Unexpected native import conflict; manual review required")
    replacements = ["    sync::{Arc, Condvar, Mutex},\n",
                    SECOND_THEIRS.replace("call_manager::{CallManager, CreateGroupCallParams}", "call_manager::CallManager")]
    for match, replacement in reversed(list(zip(matches, replacements))):
        text = text[:match.start()] + replacement + text[match.end():]
    require(not re.search(r"^(<<<<<<<|=======|>>>>>>>)", text, re.M), "Unresolved native conflict")
    return text


def patch_id(runner: Runner, source: Path, *range_args: str) -> str:
    diff = runner.git(source, "diff", "--no-ext-diff", "--no-textconv", *range_args, "--", "src/rust/src").stdout
    value = runner.git(source, "patch-id", "--stable", data=diff).stdout.decode().split()
    require(len(value) == 2, "Expected exactly one production patch ID")
    return value[0]


def verify_source(runner: Runner, source: Path) -> dict:
    lock = runner.lock
    require(runner.value(source, "rev-parse", "--show-toplevel") == str(source), "Source is not the repository root")
    require(runner.value(source, "rev-parse", "HEAD") == lock["source_commit"], "Native source commit mismatch")
    require(runner.value(source, "rev-parse", "HEAD^{tree}") == lock["source_tree"], "Native source tree mismatch")
    require(runner.value(source, "show", "-s", "--format=%P", "HEAD") == lock["base_commit"], "Unexpected native parent")
    require(not runner.value(source, "status", "--porcelain=v1", "--untracked-files=all", "--ignored"), "Native source has changed or extra files")
    upstream_id = patch_id(runner, source, lock["upstream_commit"] + "^", lock["upstream_commit"])
    actual_id = patch_id(runner, source, lock["base_commit"], "HEAD")
    require(actual_id == upstream_id == lock["production_patch_id"], "Native production change differs from Signal")
    result = {"status": "passed", "base_commit": lock["base_commit"], "upstream_commit": lock["upstream_commit"],
              "source_commit": lock["source_commit"], "source_tree": lock["source_tree"],
              "production_patch_id": actual_id, "native_build": "not_run_by_source_verification"}
    write_json(runner.proof / "source.json", result)
    return result


def prepare(runner: Runner, source: Path) -> None:
    lock = runner.lock
    require(not source.exists(), "--source-dir must be a new path")
    source.mkdir(parents=True)
    runner.git(source, "init", "--template=")
    runner.git(source, "fetch", "--no-tags", "--depth=1", lock["base_repository"], lock["base_commit"])
    runner.git(source, "fetch", "--no-tags", "--depth=2", lock["upstream_repository"], lock["upstream_commit"])
    runner.git(source, "checkout", "--detach", lock["base_commit"])
    result = runner.git(source, "cherry-pick", "-x", lock["upstream_commit"], check=False)
    amend = result.returncode == 0
    if not amend:
        require(result.returncode == 1, "Native cherry-pick failed before conflict resolution")
        require(runner.value(source, "rev-parse", "CHERRY_PICK_HEAD") == lock["upstream_commit"], "Unexpected cherry-pick state")
        require(runner.value(source, "diff", "--name-only", "--diff-filter=U") == IMPORT_PATH,
                "Native cherry-pick has an unexpected conflicted path")
        resolution = lock["test_import_resolution"]
        for stage, key in ((1, "ancestor_blob"), (2, "ours_blob"), (3, "theirs_blob")):
            require(runner.value(source, "rev-parse", f":{stage}:{IMPORT_PATH}") == resolution[key], "Unexpected import-conflict input")
        path = source / IMPORT_PATH
        resolved = resolve_test_imports(path.read_text()).encode()
        require(runner.git(source, "hash-object", "--stdin", data=resolved).stdout.decode().strip() == resolution["resolved_blob"],
                "Resolved test imports do not match the reviewed blob")
        path.write_bytes(resolved)
        runner.git(source, "add", "--", IMPORT_PATH)
    require(runner.value(source, "write-tree") == lock["source_tree"], "Reconstructed native tree differs from the lock")
    runner.git(source, "diff", "--cached", "--check")
    runner.git(source, "commit", *( ["--amend"] if amend else [] ), "--file", str(HERE / "hotfix-commit.txt"))
    verify_source(runner, source)


def artifact_files(lock: dict, maven: Path) -> dict[str, Path]:
    directory = maven / lock["artifact_group"].replace(".", "/") / lock["artifact_name"] / lock["artifact_version"]
    stem = f"{lock['artifact_name']}-{lock['artifact_version']}"
    result = {f"{stem}.{suffix}": directory / f"{stem}.{suffix}" for suffix in ("aar", "pom", "module")}
    for name, path in result.items():
        require(path.is_file() and not path.is_symlink() and path.stat().st_size > 0, f"Missing or invalid local artifact: {name}")
        require(path.resolve().is_relative_to(maven), "Local artifact escapes its Maven repository")
    pom = ET.parse(result[stem + ".pom"]).getroot()
    pns = {"p": "http://maven.apache.org/POM/4.0.0"}
    for field, value in (("groupId", lock["artifact_group"]), ("artifactId", lock["artifact_name"]), ("version", lock["artifact_version"])):
        require(pom.findtext("p:" + field, namespaces=pns) == value, f"Unexpected local POM {field}")
    module = json.loads(result[stem + ".module"].read_text())
    expected = {"group": lock["artifact_group"], "module": lock["artifact_name"], "version": lock["artifact_version"]}
    require(all(module.get("component", {}).get(key) == value for key, value in expected.items()), "Unexpected local module coordinate")
    entries = [entry for variant in module.get("variants", []) for entry in variant.get("files", [])]
    require(bool(entries), "Native module declares no artifact")
    aar = result[stem + ".aar"]
    for entry in entries:
        require(entry.get("name") == aar.name and entry.get("url") == aar.name, "Native module references an unexpected artifact")
        for algorithm in ("sha256", "sha512"):
            if algorithm in entry:
                require(hashlib.new(algorithm, aar.read_bytes()).hexdigest() == entry[algorithm], "Native module artifact checksum mismatch")
    with zipfile.ZipFile(aar) as archive:
        expected_files = {"classes.jar"} | {f"jni/{abi}/{lib}" for abi in ("armeabi-v7a", "arm64-v8a", "x86_64")
                                           for lib in ("libringrtc.so", "libringrtc_rffi.so")}
        require(expected_files.issubset(archive.namelist()), "Native AAR is missing classes or a required ABI")
        require(archive.testzip() is None, "Native AAR is corrupt")
    return result


def build(runner: Runner, source: Path, maven: Path) -> None:
    lock = runner.lock
    write_json(runner.proof / "build.json", {"status": "not_completed", "source_commit": lock["source_commit"]})
    verify_source(runner, source)
    require(shutil.which("docker") is not None, "Docker is required for the native build; source proof alone is not a build")
    require(not maven.exists(), "--maven-dir must be a new path")
    maven.mkdir(parents=True)
    image_file = runner.proof / "native-image.id"
    args = ["docker", "build", "--iidfile", str(image_file), "-f", str(source / "Dockerfile.android")]
    for variable in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
        if os.environ.get(variable):
            args += ["--build-arg", variable]
    runner.run([*args, str(source)], stream=True)
    image = image_file.read_text().strip()
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", image) is not None, "Invalid built Docker image identity")
    runner.run(["docker", "run", "--rm", "--entrypoint", "/bin/sh", image, "-c",
                "cd /ringrtc/src/rust && ./scripts/run-tests --locked"], stream=True)
    runner.run(["docker", "run", "--rm", "-e", "OVERRIDE_VERSION=" + lock["artifact_version"],
                "--mount", f"type=bind,source={maven},target=/root/.m2/repository", image,
                "assemble", "--", "--release-build"], stream=True)
    files = artifact_files(lock, maven)
    write_json(runner.proof / "build.json", {"status": "passed", "simulation_tests": "passed",
               "source_commit": lock["source_commit"], "source_tree": lock["source_tree"], "docker_image": image,
               "artifact_version": lock["artifact_version"], "artifacts": {name: sha256(path) for name, path in files.items()}})


def extend_verification(original: str, lock: dict, hashes: dict[str, str]) -> str:
    root = ET.fromstring(original)
    require(root.tag == f"{{{NS}}}verification-metadata", "Unexpected Gradle verification schema")
    configuration = root.find(f"{{{NS}}}configuration")
    require(configuration is not None and configuration.findtext(f"{{{NS}}}verify-metadata") == "true", "Metadata verification must remain enabled")
    for component in root.findall(f"{{{NS}}}components/{{{NS}}}component"):
        require((component.get("group"), component.get("name"), component.get("version")) !=
                (lock["artifact_group"], lock["artifact_name"], lock["artifact_version"]), "Hotfix verification entry already exists; use a fresh application reconstruction")
    for trust in configuration.findall(f"{{{NS}}}trusted-artifacts/{{{NS}}}trust"):
        for filename in (name for name in hashes if not name.endswith(".pom")):
            values = {"group": lock["artifact_group"], "name": lock["artifact_name"], "version": lock["artifact_version"], "file": filename}
            matches = all((re.fullmatch(trust.get(key), value) is not None if trust.get("regex") == "true" else trust.get(key) == value)
                          for key, value in values.items() if trust.get(key) is not None)
            require(not matches, "An existing trust rule skips verification of the local hotfix")
    lines = [f'      <component group="{lock["artifact_group"]}" name="{lock["artifact_name"]}" version="{lock["artifact_version"]}">']
    for name, digest in sorted(hashes.items()):
        require(re.fullmatch(r"[0-9a-f]{64}", digest) is not None, "Invalid local artifact checksum")
        lines += [f'         <artifact name="{name}">',
                  f'            <sha256 value="{digest}" origin="Local build of native tree {lock["source_tree"]}"/>',
                  '         </artifact>']
    lines.append('      </component>')
    marker = "   </components>"
    require(original.count(marker) == 1, "Unexpected verification document layout")
    return original.replace(marker, "\n".join(lines) + "\n" + marker)


def verified_artifacts(runner: Runner, maven: Path) -> tuple[dict[str, Path], dict[str, str]]:
    lock = runner.lock
    receipt_path = runner.proof / "build.json"
    require(receipt_path.is_file(), "A successful native build receipt is required")
    receipt = json.loads(receipt_path.read_text())
    require(receipt.get("status") == "passed" and receipt.get("simulation_tests") == "passed", "Native build or tests did not pass")
    for key in ("source_commit", "source_tree", "artifact_version"):
        require(receipt.get(key) == lock[key], f"Native build receipt has unexpected {key}")
    files = artifact_files(lock, maven)
    hashes = {name: sha256(path) for name, path in files.items()}
    require(hashes == receipt.get("artifacts"), "Local artifacts have changed since the native build")
    return files, hashes


def integration_material(lock: dict, app: Path, maven: Path, original: str,
                         files: dict[str, Path], hashes: dict[str, str]) -> tuple[str, str]:
    verification = app / "gradle/verification-metadata.xml"
    updated = extend_verification(original, lock, hashes)
    inputs = {"application": str(app), "repository": str(maven), "group": lock["artifact_group"], "name": lock["artifact_name"],
              "originalVersion": lock["original_version"], "version": lock["artifact_version"],
              "files": {str(path): hashes[name] for name, path in files.items()},
              "verification": str(verification), "verificationSha256": hashlib.sha256(updated.encode()).hexdigest()}
    encoded = base64.b64encode(json.dumps(inputs).encode()).decode()
    script = (HERE / "ringrtc.init.gradle").read_text().replace("NATIVE_INPUTS_BASE64", encoded)
    return updated, script


def integration_receipt(runner: Runner, app: Path, hashes: dict[str, str]) -> dict:
    return {"status": "prepared", "application": str(app), "artifacts": hashes,
            "source_tree": runner.lock["source_tree"], "init_script": str(runner.proof / "ringrtc.init.gradle"),
            "android_build": "not_run_by_integration"}


def integrate(runner: Runner, app: Path, maven: Path) -> None:
    files, hashes = verified_artifacts(runner, maven)
    verification = app / "gradle/verification-metadata.xml"
    require(verification.is_file() and not verification.is_symlink(), "Missing application verification metadata")
    original = verification.read_text()
    updated, script = integration_material(runner.lock, app, maven, original, files, hashes)
    (runner.proof / "verification-metadata.before.xml").write_text(original)
    (runner.proof / "ringrtc.init.gradle").write_text(script)
    temporary = verification.with_name("verification-metadata.native.tmp")
    require(not temporary.exists(), "Unexpected pending verification metadata write")
    temporary.write_text(updated)
    temporary.replace(verification)
    write_json(runner.proof / "integration.json", integration_receipt(runner, app, hashes))
    print(f"--dependency-verification=strict --init-script {runner.proof / 'ringrtc.init.gradle'}")


def verify_integration(runner: Runner, app: Path, maven: Path) -> dict:
    """Recheck the exact permitted working-tree transform immediately before Gradle."""
    files, hashes = verified_artifacts(runner, maven)
    original = runner.git(app, "show", "HEAD:gradle/verification-metadata.xml").stdout.decode()
    updated, script = integration_material(runner.lock, app, maven, original, files, hashes)
    expected = {app / "gradle/verification-metadata.xml": updated.encode(),
                runner.proof / "ringrtc.init.gradle": script.encode(),
                runner.proof / "verification-metadata.before.xml": original.encode()}
    for path, content in expected.items():
        require(path.is_file() and not path.is_symlink() and path.read_bytes() == content,
                f"Native integration input differs from the pinned transformation: {path}")
    receipt = json.loads((runner.proof / "integration.json").read_text())
    require(receipt == integration_receipt(runner, app, hashes), "Native integration receipt differs from expected inputs")
    return {"status": "passed", "verification_sha256": hashlib.sha256(updated.encode()).hexdigest(),
            "init_sha256": hashlib.sha256(script.encode()).hexdigest(), "source_tree": runner.lock["source_tree"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify-source", "build", "integrate", "verify-integration"))
    parser.add_argument("--lock", type=Path, default=Path("native-ringrtc.json"))
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--proof-dir", required=True, type=Path)
    parser.add_argument("--maven-dir", type=Path)
    parser.add_argument("--app-dir", type=Path)
    args = parser.parse_args()
    proof = args.proof_dir.resolve()
    try:
        lock = read_lock(args.lock)
        source = args.source_dir.resolve() if args.source_dir else None
        maven = args.maven_dir.resolve() if args.maven_dir else None
        app = args.app_dir.resolve() if args.app_dir else None
        if source:
            require(not proof.is_relative_to(source) and not source.is_relative_to(proof), "Source and proof directories must be separate")
        runner = Runner(proof, lock)
        if args.command in ("integrate", "verify-integration"):
            require(app is not None and maven is not None, args.command + " needs --app-dir and --maven-dir")
            (integrate if args.command == "integrate" else verify_integration)(runner, app, maven)
        else:
            require(source is not None, args.command + " needs --source-dir")
            if args.command == "prepare":
                prepare(runner, source)
            elif args.command == "verify-source":
                verify_source(runner, source)
            else:
                require(maven is not None, "build needs --maven-dir")
                build(runner, source, maven)
        return 0
    except (Failure, OSError, ValueError, KeyError, ET.ParseError, zipfile.BadZipFile) as error:
        print(f"native hotfix: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
