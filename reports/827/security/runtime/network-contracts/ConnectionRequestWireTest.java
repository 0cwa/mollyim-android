import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import im.molly.unifiedpush.model.ConnectionRequest;
import im.molly.unifiedpush.model.Response;
import im.molly.unifiedpush.model.ConnectionResult;
import org.signal.core.util.JsonUtils;

import java.util.Set;
import java.util.HashSet;

/** Executes the candidate's compiled DTO plus the app's compiled JsonUtils; fake values only. */
public final class ConnectionRequestWireTest {
  public static void main(String[] args) throws Exception {
    ConnectionRequest req = new ConnectionRequest("FAKE-ACI", 7, "FAKE-PASSWORD", "https://push.invalid/fake", true);
    String json = JsonUtils.toJson(req);
    JsonNode root = new ObjectMapper().readTree(json);
    Set<String> keys = new HashSet<>();
    root.fieldNames().forEachRemaining(keys::add);
    Set<String> expected = Set.of("uuid", "device_id", "password", "endpoint", "ping");
    require(keys.equals(expected), "request keys mismatch: " + keys);
    require(root.get("uuid").asText().equals("FAKE-ACI"), "uuid value");
    require(root.get("device_id").asInt() == 7, "device id");
    require(root.get("password").asText().equals("FAKE-PASSWORD"), "password value");
    require(root.get("endpoint").asText().equals("https://push.invalid/fake"), "endpoint value");
    require(root.get("ping").asBoolean(), "ping value");

    Response response = JsonUtils.fromJson("{\"mollysocket\":{\"version\":\"1.2.3\",\"status\":\"ok\"}}", Response.class);
    require(response.getMollySocket().getStatus() == ConnectionResult.OK, "lower-case status response mapping");
    System.out.println("PASS: candidate DTO serialized exact MollySocket key/value contract; JsonUtils decoded lowercase status=ok");
  }
  private static void require(boolean condition, String message) {
    if (!condition) throw new AssertionError(message);
  }
}
