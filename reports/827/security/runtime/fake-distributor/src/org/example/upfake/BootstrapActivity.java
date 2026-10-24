package org.example.upfake;

import android.app.Activity;
import android.os.Bundle;

/** Starts once so Android does not treat this freshly installed fixture as stopped. */
public final class BootstrapActivity extends Activity {
  @Override protected void onCreate(Bundle state) {
    super.onCreate(state);
    finish();
  }
}
