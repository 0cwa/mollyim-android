import im.molly.unifiedpush.MollySocketRepository;
import im.molly.unifiedpush.model.MollySocketDevice;
import org.thoughtcrime.securesms.linkdevice.LinkDeviceRepository;
import java.io.IOException;
public final class RemoveDeviceFlowTest {
  public static void main(String[] args) throws Exception {
    MollySocketDevice d = new MollySocketDevice(42, "FAKE-PASSWORD");
    LinkDeviceRepository.removeResult = false;
    boolean threw = false;
    try { MollySocketRepository.INSTANCE.removeDevice(d); } catch (IOException e) { threw = true; }
    if (!threw) throw new AssertionError("false unlink result must throw for retry");
    if (LinkDeviceRepository.INSTANCE.lastDeviceId != 42) throw new AssertionError("wrong device id");
    LinkDeviceRepository.removeResult = true;
    MollySocketRepository.INSTANCE.removeDevice(d);
    if (LinkDeviceRepository.INSTANCE.lastDeviceId != 42) throw new AssertionError("success path did not invoke unlink");
    System.out.println("PASS: actual compiled candidate MollySocketRepository.removeDevice throws IOException when fake LinkDeviceRepository returns false; true result returns normally. Fixtures only.");
  }
}
