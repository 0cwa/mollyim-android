#!/usr/bin/env python3
"""Validate canonical exported Quickstart JSON without printing its values."""
import base64
import hashlib
import json
import pathlib
import sys

if len(sys.argv) != 2:
    raise SystemExit(f"usage: {sys.argv[0]} FIXTURE_DIRECTORY")
root = pathlib.Path(sys.argv[1])
expected_names = {"prod_synthetic.json", "staging_synthetic.json"}
expected_types = {
    "aci": str,
    "pni": str,
    "e164": str,
    "servicePassword": str,
    "aciIdentityKeyPair": str,
    "pniIdentityKeyPair": str,
    "aciSignedPreKey": str,
    "aciLastResortKyberPreKey": str,
    "pniSignedPreKey": str,
    "pniLastResortKyberPreKey": str,
    "profileKey": str,
    "registrationId": int,
    "pniRegistrationId": int,
    "profileGivenName": str,
    "profileFamilyName": str,
    "accountEntropyPool": (str, type(None)),
}
files = sorted(root.glob("*.json"))
if {p.name for p in files} != expected_names:
    raise SystemExit("FAIL: expected exactly the two synthetic flavor filenames")
for path in files:
    raw = path.read_bytes()
    data = json.loads(raw)
    if set(data) != set(expected_types):
        raise SystemExit("FAIL: field set differs from pinned QuickstartCredentials schema")
    for key, kind in expected_types.items():
        valid = type(data[key]) is int if kind is int else isinstance(data[key], kind)
        if not valid:
            raise SystemExit("FAIL: field types differ from pinned QuickstartCredentials schema")
    if not data["aci"] or not data["pni"] or data["e164"] != "+15555559999":
        raise SystemExit("FAIL: synthetic local account marker missing")
    if not all(data[key] for key in ("servicePassword", "profileKey", "profileGivenName")):
        raise SystemExit("FAIL: required synthetic account field empty")
    for key in (
        "aciIdentityKeyPair", "pniIdentityKeyPair", "aciSignedPreKey",
        "aciLastResortKyberPreKey", "pniSignedPreKey", "pniLastResortKyberPreKey",
        "profileKey",
    ):
        try:
            base64.b64decode(data[key], validate=True)
        except Exception as exc:
            raise SystemExit("FAIL: invalid base64 field") from exc
    print(f"PASS {path.name}: schema/types/base64; bytes={len(raw)} sha256={hashlib.sha256(raw).hexdigest()}")
