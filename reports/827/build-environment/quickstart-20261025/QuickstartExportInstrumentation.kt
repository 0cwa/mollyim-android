package org.thoughtcrime.securesms.quickstartfixture

import android.app.Instrumentation
import android.content.Context
import android.content.Intent
import android.os.Bundle
import java.io.File
import java.lang.reflect.InvocationTargetException
import java.security.MessageDigest

class QuickstartExportInstrumentation : Instrumentation() {
  override fun onCreate(arguments: Bundle) {
    super.onCreate(arguments)
    start()
  }

  override fun onStart() {
    waitForIdleSync()
    val target = targetContext
    val response = Bundle()
    var status = 0
    try {
      check(target.packageName == "org.thoughtcrime.securesms.benchmark")
      val loader = target.classLoader
      val setup = Intent().setClassName(target.packageName, "org.signal.benchmark.BenchmarkSetupActivity")
        .putExtra("setup-type", "message-send")
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
      startActivitySync(setup)
      val deadline = android.os.SystemClock.uptimeMillis() + 60_000
      var ready = false
      while (android.os.SystemClock.uptimeMillis() < deadline) {
        val store = loader.loadClass("org.thoughtcrime.securesms.keyvalue.SignalStore")
        val accountValues = store.getMethod("account").invoke(null)
        val registered = accountValues.javaClass.getMethod("isRegistered").invoke(accountValues) as Boolean
        if (registered) { ready = true; break }
        android.os.SystemClock.sleep(100)
      }
      check(ready)

      val exporterClass = loader.loadClass("org.thoughtcrime.securesms.registration.data.QuickstartCredentialExporter")
      val exporter = exporterClass.getField("INSTANCE").get(null)
      val output = exporterClass.getMethod("export", Context::class.java).invoke(exporter, target) as File
      check(output.isFile && output.length() > 0L)

      val digest = MessageDigest.getInstance("SHA-256").digest(output.readBytes())
        .joinToString("") { "%02x".format(it) }
      response.putString("fixture_status", "PASS")
      response.putLong("fixture_size_bytes", output.length())
      response.putString("fixture_sha256", digest)
      response.putString("generator", "TestUsers.setupSelf + QuickstartCredentialExporter")
    } catch (t: Throwable) {
      status = 1
      val cause = if (t is InvocationTargetException) t.targetException else t
      response.putString("fixture_status", "FAIL")
      response.putString("failure_type", cause.javaClass.name)
    }
    finish(status, response)
  }
}
