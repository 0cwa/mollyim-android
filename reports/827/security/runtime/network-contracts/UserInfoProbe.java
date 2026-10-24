import com.sun.net.httpserver.HttpsServer;
import com.sun.net.httpserver.HttpsConfigurator;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import javax.net.ssl.*;
import java.io.FileInputStream;
import java.net.InetSocketAddress;
import java.security.KeyStore;
import java.util.concurrent.atomic.AtomicReference;

public class UserInfoProbe {
  public static void main(String[] args) throws Exception {
    KeyStore ks = KeyStore.getInstance("JKS");
    try (FileInputStream in = new FileInputStream("/workspace/work/p2-review/local-test.jks")) { ks.load(in, "fakeonly".toCharArray()); }
    KeyManagerFactory kmf = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm()); kmf.init(ks, "fakeonly".toCharArray());
    TrustManagerFactory tmf = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm()); tmf.init(ks);
    X509TrustManager trust = (X509TrustManager) tmf.getTrustManagers()[0];
    SSLContext ssl = SSLContext.getInstance("TLS"); ssl.init(kmf.getKeyManagers(), tmf.getTrustManagers(), null);
    AtomicReference<String> authorization = new AtomicReference<>();
    AtomicReference<String> uri = new AtomicReference<>();
    HttpsServer server = HttpsServer.create(new InetSocketAddress("localhost", 0), 0);
    server.setHttpsConfigurator(new HttpsConfigurator(ssl));
    server.createContext("/resource", ex -> {
      authorization.set(ex.getRequestHeaders().getFirst("Authorization"));
      uri.set(ex.getRequestURI().toString());
      byte[] body = "ok".getBytes(); ex.sendResponseHeaders(200, body.length); ex.getResponseBody().write(body); ex.close();
    });
    server.start();
    try {
      String url = "https://FAKEUSER:FAKEPASS@localhost:" + server.getAddress().getPort() + "/resource#FAKEFRAGMENT";
      Request request = new Request.Builder().url(url).build();
      try (var response = new OkHttpClient.Builder().sslSocketFactory(ssl.getSocketFactory(), trust).build().newCall(request).execute()) {
        System.out.println("response=" + response.code());
      }
      System.out.println("authorization_header_present=" + (authorization.get() != null));
      System.out.println("request_target=" + uri.get());
      System.out.println("fragment_was_sent=" + (uri.get() != null && uri.get().contains("FAKEFRAGMENT")));
    } finally { server.stop(0); }
  }
}
