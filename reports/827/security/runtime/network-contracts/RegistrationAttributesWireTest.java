import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.signal.core.util.JsonUtils;
import org.whispersystems.signalservice.api.account.AccountAttributes;
import org.whispersystems.signalservice.api.account.DeviceAttributes;
import java.util.HashSet;
import java.util.Set;

/** Serializes the candidate's actual compiled registration attribute DTO with fixture values only. */
public final class RegistrationAttributesWireTest {
  public static void main(String[] args) throws Exception {
    AccountAttributes.Capabilities caps = new AccountAttributes.Capabilities(false, true, false, false, true);
    DeviceAttributes attrs = new DeviceAttributes(true, 1234, 5678, "FAKE-DEVICE-NAME", caps);
    String json = JsonUtils.toJson(attrs);
    JsonNode node = new ObjectMapper().readTree(json);
    Set<String> keys = new HashSet<>();
    node.fieldNames().forEachRemaining(keys::add);
    Set<String> expected = Set.of("fetchesMessages", "registrationId", "pniRegistrationId", "name", "capabilities");
    if (!keys.equals(expected)) throw new AssertionError("fields " + keys);
    if (node.get("fetchesMessages").asBoolean() != true) throw new AssertionError("fetchesMessages");
    if (node.get("registrationId").asInt() != 1234) throw new AssertionError("registrationId");
    if (node.get("pniRegistrationId").asInt() != 5678) throw new AssertionError("pniRegistrationId");
    if (!node.get("name").asText().equals("FAKE-DEVICE-NAME")) throw new AssertionError("name");
    System.out.println("PASS: candidate DeviceAttributes compiled model serializes five expected fields; " + json);
  }
}
