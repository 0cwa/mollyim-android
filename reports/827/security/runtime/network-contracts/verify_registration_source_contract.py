#!/usr/bin/env python3
"""Compare candidate16's compiled registration DTO JSON to pinned Signal-Server source."""
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER = HERE / "server-source-evidence"
RUN_DTO = HERE / "run-registration-attributes-test.sh"
LOG = HERE / "registration-attributes-test.log"

# Re-run serialization against the actual candidate16 compiled DeviceAttributes + JsonUtils.
subprocess.run([str(RUN_DTO)], check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
line = LOG.read_text().strip()
json_text = line.split("; ", 1)[1]
candidate = json.loads(json_text)
candidate_fields = set(candidate)

link_request = (SERVER / "LinkDeviceRequest.java").read_text()
server_attrs = (SERVER / "DeviceAttributes.java").read_text()
controller = (SERVER / "DeviceController.java").read_text()
mapper = (SERVER / "SystemMapper.java").read_text()

assert re.search(r'@JsonProperty\("accountAttributes"\)\s+DeviceAttributes deviceAttributes', link_request), \
    "server request must bind nested accountAttributes to DeviceAttributes"
record = re.search(r"public record DeviceAttributes\((.*?)\)\s*\{", server_attrs, re.S)
assert record, "server DeviceAttributes record declaration not found"
# These names are the serialized DTO field names, including the explicit JSON alias.
server_fields = {"fetchesMessages", "registrationId", "pniRegistrationId", "name", "capabilities"}
record_text = record.group(1)
assert "boolean fetchesMessages" in record_text
assert "int registrationId" in record_text
assert '@JsonProperty("pniRegistrationId") int phoneNumberIdentityRegistrationId' in record_text
assert re.search(r"byte\[\] name", record_text)
assert re.search(r"Set<DeviceCapability> capabilities", record_text)
assert candidate_fields == server_fields, f"candidate={sorted(candidate_fields)} server={sorted(server_fields)}"

# The linked-device controller constructs DeviceSpec from the five DTO values and activation fields.
link_pos = controller.index('@Path("/link")')
body_start = controller.index("public LinkDeviceResponse linkDevice", link_pos)
body_end = controller.index("\n  @GET\n  @Path(\"/wait_for_linked_device", body_start)
link_method = controller[body_start:body_end]
for accessor in ("name()", "capabilities()", "registrationId()", "phoneNumberIdentityRegistrationId()", "fetchesMessages()"):
    assert f"deviceAttributes.{accessor}" in link_method, f"linked-device method does not consume {accessor}"
for irrelevant in ("voice", "video", "unrestrictedUnidentifiedAccess", "discoverableByPhoneNumber", "registrationLock", "unidentifiedAccessKey", "recoveryPassword"):
    assert irrelevant not in link_method, f"unexpected linked-device read: {irrelevant}"
assert "FAIL_ON_UNKNOWN_PROPERTIES, false" in mapper
print("PASS: candidate16 compiled DTO JSON fields exactly match pinned Signal-Server DeviceAttributes; linked-device handler consumes those five fields, ignores the listed account-only extras, and server mapper ignores unknown JSON properties.")
print("LIMIT: source contract check only; does not identify the deployed server build or prove a live registration.")
