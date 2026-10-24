package org.example.upfake;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Log;

/** Local-only UnifiedPush protocol fixture. It deliberately has no INTERNET permission. */
public final class DistributorReceiver extends BroadcastReceiver {
  private static final String TAG = "UPFakeDistributor";
  private static final String PREFS = "fixture";
  private static final String REGISTER = "org.unifiedpush.android.distributor.REGISTER";
  private static final String UNREGISTER = "org.unifiedpush.android.distributor.UNREGISTER";
  private static final String NEW_ENDPOINT = "org.unifiedpush.android.connector.NEW_ENDPOINT";
  private static final String MESSAGE = "org.unifiedpush.android.connector.MESSAGE";
  private static final String UNREGISTERED = "org.unifiedpush.android.connector.UNREGISTERED";
  private static final String TEST_MESSAGE = "org.example.upfake.TEST_MESSAGE";
  private static final String TEST_UNREGISTERED = "org.example.upfake.TEST_UNREGISTERED";

  @Override public void onReceive(Context context, Intent request) {
    String action = request.getAction();
    SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    if (REGISTER.equals(action)) {
      String token = request.getStringExtra("token");
      String app = request.getStringExtra("application");
      if (token == null || app == null) {
        Log.e(TAG, "REGISTER missing token/application");
        return;
      }
      prefs.edit().putString("token", token).putString("application", app).apply();
      Log.i(TAG, "REGISTER received; token stored locally");
      Intent event = new Intent(NEW_ENDPOINT).setPackage(app)
          .putExtra("token", token)
          .putExtra("endpoint", "https://127.0.0.1/up-test-endpoint")
          .putExtra("id", "synthetic-up-fixture");
      context.sendBroadcast(event);
    } else if (UNREGISTER.equals(action)) {
      String token = request.getStringExtra("token");
      String app = prefs.getString("application", null);
      Log.i(TAG, "UNREGISTER received");
      if (token != null && app != null) {
        context.sendBroadcast(new Intent(UNREGISTERED).setPackage(app).putExtra("token", token));
      }
      prefs.edit().clear().apply();
    } else if (TEST_MESSAGE.equals(action)) {
      String token = prefs.getString("token", null);
      String app = prefs.getString("application", null);
      if (token == null || app == null) {
        Log.e(TAG, "Cannot send MESSAGE before REGISTER");
        return;
      }
      byte[] body = "{\"test\":true}".getBytes(java.nio.charset.StandardCharsets.UTF_8);
      context.sendBroadcast(new Intent(MESSAGE).setPackage(app)
          .putExtra("token", token).putExtra("bytesMessage", body)
          .putExtra("id", "synthetic-message-1"));
      Log.i(TAG, "Synthetic MESSAGE sent");
    } else if (TEST_UNREGISTERED.equals(action)) {
      String token = prefs.getString("token", null);
      String app = prefs.getString("application", null);
      if (token == null || app == null) {
        Log.e(TAG, "Cannot send UNREGISTERED before REGISTER");
        return;
      }
      context.sendBroadcast(new Intent(UNREGISTERED).setPackage(app).putExtra("token", token));
      Log.i(TAG, "Synthetic UNREGISTERED sent; fixture state retained for cleanup");
    }
  }
}
