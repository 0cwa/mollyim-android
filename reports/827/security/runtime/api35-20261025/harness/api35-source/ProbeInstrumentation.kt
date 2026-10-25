package org.thoughtcrime.securesms.probe

import android.app.Application
import android.app.Instrumentation
import android.app.NotificationManager
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ClipDescription
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.os.Bundle
import android.os.SystemClock
import org.json.JSONArray
import org.json.JSONObject
import java.lang.reflect.InvocationTargetException
import java.util.UUID
import java.util.function.Function

class ProbeInstrumentation : Instrumentation() {
  private val results = mutableListOf<String>()
  private val failures = mutableListOf<String>()
  private var phase: String = "seed"

  override fun onCreate(arguments: Bundle) {
    super.onCreate(arguments)
    phase = arguments.getString("phase") ?: "seed"
    start()
  }

  override fun onStart() {
    waitForIdleSync()
    val target = targetContext
    try {
      assertThat(target.packageName == TARGET_PACKAGE, "target package mismatch")
      when (phase) {
        "seed" -> runSeedPhase(target)
        "restart" -> runRestartPhase(target)
        "cleanup" -> restoreFixture(target)
        else -> throw ProbeFailure("unknown phase")
      }
    } catch (t: Throwable) {
      fail("instrumentation", unwrap(t))
      if (phase == "restart" || phase == "cleanup") {
        try {
          restoreFixture(target)
        } catch (cleanup: Throwable) {
          fail("cleanup", unwrap(cleanup))
        }
      }
    }

    val response = Bundle().apply {
      putString("probe_phase", phase)
      putString("probe_result", if (failures.isEmpty()) "PASS" else "FAIL")
      putString("probe_checks", results.joinToString("; "))
      putString("probe_failures", failures.joinToString("; "))
      putString("probe_disclaimer", "Synthetic local-only instrumentation; no real distributor, credentials, or server.")
    }
    finish(if (failures.isEmpty()) 0 else 1, response)
  }

  private fun runSeedPhase(target: Context) {
    waitForBenchmarkUnlocked(target)
    results += "PASS benchmark synthetic app unlocked"
    runCheck("delivery enum roundtrip") { testDeliveryEnum(target) }
    runCheck("preferred-method fallback") { testPreferredFallback(target) }
    runCheck("UnifiedPush backup exclusion") { testBackupExclusion(target) }
    runCheck("synthetic clipboard payloads") { testClipboard(target) }
    runCheck("fake distributor REGISTER and NEW_ENDPOINT") { prepareConnectorFixture(target) }
    runCheck("fake distributor MESSAGE and test notification") { dispatchSyntheticTestMessage(target, expectRestart = false) }
  }

  private fun runRestartPhase(target: Context) {
    waitForBenchmarkUnlocked(target)
    results += "PASS benchmark synthetic app unlocked after process restart"
    runCheck("connector token persisted across target process restart") {
      val probe = testPrefs()
      assertThat(probe.getString(KEY_INSTANCE, null) != null, "probe instance missing")
      val prefs = target.getSharedPreferences(CONNECTOR_PREFS, Context.MODE_PRIVATE)
      val instance = requireNotNull(probe.getString(KEY_INSTANCE, null))
      assertThat(prefs.getString("$instance/unifiedpush.connector", null) != null, "local connector registration did not survive restart")
      assertThat(unifiedValues(target).javaClass.getMethod("getEndpoint").invoke(unifiedValues(target)) == FAKE_ENDPOINT, "synthetic endpoint did not survive target process restart")
    }
    runCheck("fake distributor MESSAGE after process restart") { dispatchSyntheticTestMessage(target, expectRestart = true) }
    runCheck("fake distributor UNREGISTER and endpoint removal") { unregisterFixture(target) }
    runCheck("refresh-job transition to WebSocket availability") { testRefreshFallback(target) }
    runCheck("restore test-only target state") { restoreFixture(target) }
  }

  private fun testDeliveryEnum(target: Context) {
    val loader = target.classLoader
    val enumClass = loader.loadClass(DELIVERY_METHOD)
    val entries = enumClass.getMethod("values").invoke(null) as Array<*>
    val serialize = enumClass.getMethod("serialize")
    val deserialize = enumClass.getMethod("deserialize", String::class.java)
    assertThat(entries.map { it.toString() } == listOf("FCM", "WEBSOCKET", "UNIFIEDPUSH"), "delivery enum values differ")
    entries.forEach { value ->
      val serialized = serialize.invoke(value) as String
      val restored = deserialize.invoke(null, serialized)
      assertThat(restored == value, "delivery enum roundtrip failed for ${value}")
    }
  }

  private fun testPreferredFallback(target: Context) {
    val (settings, account) = signalValues(target)
    val hadMethod = settings.javaClass.getMethod("hasPreferredNotificationMethod").invoke(settings) as Boolean
    val oldMethod = settings.javaClass.getMethod("getPreferredNotificationMethod").invoke(settings)
    val oldFcm = account.javaClass.getMethod("isFcmEnabled").invoke(account) as Boolean
    try {
      removeStoreKey(settings, METHOD_KEY)
      setFcm(account, false)
      flushSignalStore(target)
      assertThat(!(settings.javaClass.getMethod("hasPreferredNotificationMethod").invoke(settings) as Boolean), "preference key should be absent for fallback")
      assertThat(settings.javaClass.getMethod("getPreferredNotificationMethod").invoke(settings).toString() == "WEBSOCKET", "no-FCM fallback should be WebSocket")
      setFcm(account, true)
      flushSignalStore(target)
      assertThat(settings.javaClass.getMethod("getPreferredNotificationMethod").invoke(settings).toString() == "FCM", "FCM-enabled fallback should be FCM")
      val unifiedPush = enumValue(target, DELIVERY_METHOD, "UNIFIEDPUSH")
      settings.javaClass.getMethod("setPreferredNotificationMethod", unifiedPush.javaClass).invoke(settings, unifiedPush)
      flushSignalStore(target)
      assertThat(settings.javaClass.getMethod("getPreferredNotificationMethod").invoke(settings) == unifiedPush, "explicit UnifiedPush selection should persist")
    } finally {
      if (hadMethod) {
        settings.javaClass.getMethod("setPreferredNotificationMethod", oldMethod.javaClass).invoke(settings, oldMethod)
      } else {
        removeStoreKey(settings, METHOD_KEY)
      }
      setFcm(account, oldFcm)
      flushSignalStore(target)
    }
  }

  private fun testBackupExclusion(target: Context) {
    val unified = staticValue(target, SIGNAL_STORE, "unifiedpush")
    val keys = unified.javaClass.getMethod("getKeysToIncludeInBackup").invoke(unified) as List<*>
    assertThat(keys.isEmpty(), "UnifiedPush values must not be included in account backup")
  }

  private fun testClipboard(target: Context) {
    val foregroundActivity = startTargetActivityAndWaitForFocus(target)
    assertThat(foregroundActivity.packageName == target.packageName, "clipboard activity is not in target app")
    val (settings, account) = signalValues(target)
    val aci = account.javaClass.getMethod("getAci").invoke(account)?.toString()
    assertThat(!aci.isNullOrBlank(), "benchmark synthetic account is not seeded")

    val unified = staticValue(target, SIGNAL_STORE, "unifiedpush")
    val originalDevice = unified.javaClass.getMethod("getDevice").invoke(unified)
    val originalEndpoint = unified.javaClass.getMethod("getEndpoint").invoke(unified)
    val fakeId = 8271
    val fakePassword = "instrumentation-only-marker"
    val fakeEndpoint = "https://invalid.example/probe-endpoint"
    val fakeDeviceClass = target.classLoader.loadClass("im.molly.unifiedpush.model.MollySocketDevice")
    val fakeDevice = fakeDeviceClass.getConstructor(Int::class.javaPrimitiveType, String::class.java).newInstance(fakeId, fakePassword)
    val clipboard = target.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager

    try {
      unified.javaClass.getMethod("setDevice", fakeDeviceClass).invoke(unified, fakeDevice)
      unified.javaClass.getMethod("setEndpoint", String::class.java).invoke(unified, fakeEndpoint)
      flushSignalStore(target)

      val viewModelClass = target.classLoader.loadClass(SETTINGS_VIEW_MODEL)
      val application = target.applicationContext as Application
      val viewModel = viewModelClass.getConstructor(Application::class.java).newInstance(application)
      val expectedParameters = "connection add $aci $fakeId $fakePassword $fakeEndpoint"
      runOnMainSync { viewModelClass.getMethod("copyParamsToClipboard", Context::class.java).invoke(viewModel, target) }
      assertClip(clipboard, "Server parameters", expectedParameters)
      assertSensitiveClipboardMetadata(clipboard)
      runOnMainSync { viewModelClass.getMethod("copyAciToClipboard", Context::class.java).invoke(viewModel, target) }
      assertClip(clipboard, "Account ID", aci!!)
      assertSensitiveClipboardMetadata(clipboard)
      val sdk = android.os.Build.VERSION.SDK_INT
      if (sdk == 30) {
        val expiryDeadline = SystemClock.uptimeMillis() + 65_000L
        while (SystemClock.uptimeMillis() < expiryDeadline && clipboard.primaryClip?.getItemAt(0)?.text?.toString() == aci) {
          SystemClock.sleep(250)
        }
        val expired = clipboard.primaryClip
        assertThat(expired == null || expired.itemCount == 0 || expired.getItemAt(0).text?.toString() != aci, "sensitive clipboard content was not cleared by its scheduled 60-second alarm")
      } else {
        assertThat(sdk >= 33, "clipboard metadata probe requires Android 13 or later")
        results += "PASS API33+ sensitive clipboard metadata for parameters and account ID"
      }
    } finally {
      runOnMainSync { clipboard.setPrimaryClip(ClipData.newPlainText("", "")) }
      unified.javaClass.getMethod("setDevice", fakeDeviceClass).invoke(unified, originalDevice)
      unified.javaClass.getMethod("setEndpoint", String::class.java).invoke(unified, originalEndpoint)
      flushSignalStore(target)
    }
  }

  private fun startTargetActivityAndWaitForFocus(target: Context): android.app.Activity {
    // Benchmark variants do not declare a MAIN/LAUNCHER activity. Start the app's
    // explicit MainActivity; getLaunchIntentForPackage resolves unrelated setup/restore flows.
    val launchIntent = Intent().setClassName(target.packageName, "org.thoughtcrime.securesms.MainActivity")
    launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    val activity = startActivitySync(launchIntent)
    waitUntil("target launcher activity window focus", 20_000) {
      var focused = false
      runOnMainSync {
        focused = activity.hasWindowFocus() && activity.window?.decorView?.hasWindowFocus() == true
      }
      focused
    }
    return activity
  }

  private fun prepareConnectorFixture(target: Context) {
    val probe = testPrefs()
    val prefs = target.getSharedPreferences(CONNECTOR_PREFS, Context.MODE_PRIVATE)
    val unified = unifiedValues(target)
    if (probe.getString(KEY_SNAPSHOT, null) == null) {
      probe.edit()
        .putString(KEY_SNAPSHOT, snapshotPreferences(prefs).toString())
        .putLong(KEY_ORIGINAL_LAST_RECEIVED, unified.javaClass.getMethod("getLastReceivedTime").invoke(unified) as Long)
        .putString(KEY_ORIGINAL_ENDPOINT, unified.javaClass.getMethod("getEndpoint").invoke(unified) as String?)
        .commit()
    }
    assertThat(unified.javaClass.getMethod("getEndpoint").invoke(unified) == null, "fixture requires an empty original UnifiedPush endpoint")

    val connectorClass = target.classLoader.loadClass(UNIFIED_PUSH_API)
    connectorClass.getMethod("saveDistributor", Context::class.java, String::class.java)
      .invoke(null, target, FAKE_DISTRIBUTOR)
    connectorClass.getMethod("registerApp", Context::class.java, String::class.java, String::class.java, String::class.java)
      .invoke(null, target, INSTANCE, null, null)

    val token = prefs.getString("$INSTANCE/unifiedpush.connector", null)
    assertThat(!token.isNullOrBlank(), "connector did not create a local token")
    val instances = prefs.getStringSet("unifiedpush.instances", emptySet()) ?: emptySet()
    assertThat(INSTANCE in instances, "connector did not retain the probe instance mapping")
    waitUntil("fake distributor NEW_ENDPOINT") {
      unified.javaClass.getMethod("getEndpoint").invoke(unified) == FAKE_ENDPOINT
    }
    probe.edit().putString(KEY_INSTANCE, INSTANCE).commit()
    results += "PASS local REGISTER/NEW_ENDPOINT (fake distributor; no network)"
  }

  private fun dispatchSyntheticTestMessage(target: Context, expectRestart: Boolean) {
    val account = staticValue(target, SIGNAL_STORE, "account")
    val isRegistered = account.javaClass.getMethod("isRegistered").invoke(account) as Boolean
    assertThat(isRegistered, "benchmark local synthetic account is not registered")
    assertThat(!isTargetLocked(target), "benchmark app must be unlocked for test-message branch")

    val probe = testPrefs()
    val instance = requireNotNull(probe.getString(KEY_INSTANCE, null))
    val prefs = target.getSharedPreferences(CONNECTOR_PREFS, Context.MODE_PRIVATE)
    val token = prefs.getString("$instance/unifiedpush.connector", null)
    assertThat(!token.isNullOrBlank(), "probe token missing")
    assertThat(instance == INSTANCE, "unexpected synthetic instance")

    val unified = unifiedValues(target)
    val oldTime = unified.javaClass.getMethod("getLastReceivedTime").invoke(unified) as Long
    unified.javaClass.getMethod("setLastReceivedTime", Long::class.javaPrimitiveType).invoke(unified, 0L)
    flushSignalStore(target)

    val notificationManager = target.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
    notificationManager.cancel(TEST_NOTIFICATION_ID)
    val fakeIntent = Intent(ACTION_FAKE_MESSAGE).setPackage(FAKE_DISTRIBUTOR)
    target.sendBroadcast(fakeIntent)
    waitUntil("candidate receiver message callback") {
      (unified.javaClass.getMethod("getLastReceivedTime").invoke(unified) as Long) > 0L &&
        notificationManager.activeNotifications.any { it.id == TEST_NOTIFICATION_ID }
    }

    val newTime = unified.javaClass.getMethod("getLastReceivedTime").invoke(unified) as Long
    assertThat(newTime > 0L, "candidate receiver did not update UnifiedPush last-received time")
    val hasTestNotification = notificationManager.activeNotifications.any { it.id == TEST_NOTIFICATION_ID }
    assertThat(hasTestNotification, "candidate receiver did not post test notification id $TEST_NOTIFICATION_ID")
    results += if (expectRestart) "PASS fake MESSAGE callback after process restart" else "PASS fake MESSAGE callback"

    if (!expectRestart) {
      probe.edit().putLong(KEY_SEED_RECEIVED_TIME, oldTime).commit()
    }
  }

  private fun unregisterFixture(target: Context) {
    val probe = testPrefs()
    val instance = requireNotNull(probe.getString(KEY_INSTANCE, null))
    val connectorPrefs = target.getSharedPreferences(CONNECTOR_PREFS, Context.MODE_PRIVATE)
    val token = connectorPrefs.getString("$instance/unifiedpush.connector", null)
    assertThat(!token.isNullOrBlank(), "probe token missing before synthetic UNREGISTERED callback")

    target.sendBroadcast(Intent(ACTION_FAKE_UNREGISTERED).setPackage(FAKE_DISTRIBUTOR))
    val unified = unifiedValues(target)
    waitUntil("fake distributor unsolicited UNREGISTERED callback") {
      unified.javaClass.getMethod("getEndpoint").invoke(unified) == null
    }
    val connectorClass = target.classLoader.loadClass(UNIFIED_PUSH_API)
    assertThat(connectorClass.getMethod("getSavedDistributor", Context::class.java).invoke(null, target) == null, "candidate callback did not remove saved distributor")
    assertThat(connectorPrefs.getString("$instance/unifiedpush.connector", null) == null, "candidate callback did not clear local connector mapping")

    // The callback removed the local token before distributor acknowledgement. Invoke the public API
    // afterward to verify idempotent local cleanup; this call no longer proves a remote ack.
    connectorClass.getMethod("unregisterApp", Context::class.java, String::class.java)
      .invoke(null, target, INSTANCE)
    results += "PASS unsolicited local UNREGISTERED callback and public API cleanup"
  }

  private fun testRefreshFallback(target: Context) {
    val (settings, account) = signalValues(target)
    val unified = unifiedValues(target)
    val hasMethod = settings.javaClass.getMethod("hasPreferredNotificationMethod").invoke(settings) as Boolean
    val oldMethod = settings.javaClass.getMethod("getPreferredNotificationMethod").invoke(settings)
    val oldFcmEnabled = account.javaClass.getMethod("isFcmEnabled").invoke(account) as Boolean
    val oldEnabled = unified.javaClass.getMethod("isEnabled").invoke(unified) as Boolean
    val oldStatus = unified.javaClass.getMethod("getRegistrationStatus").invoke(unified)
    val oldDevice = unified.javaClass.getMethod("getDevice").invoke(unified)
    val oldVapid = unified.javaClass.getMethod("getVapidPublicKey").invoke(unified)
    val oldSocket = unified.javaClass.getMethod("getMollySocketUrl").invoke(unified)
    val oldAirGapped = unified.javaClass.getMethod("getAirGapped").invoke(unified) as Boolean

    assertThat(account.javaClass.getMethod("isRegistered").invoke(account) as Boolean, "benchmark fixture must have a registered synthetic account")
    assertThat(unified.javaClass.getMethod("getEndpoint").invoke(unified) == null, "fallback fixture expects endpoint cleared by UNREGISTERED")
    try {
      val unifiedPushMethod = enumValue(target, DELIVERY_METHOD, "UNIFIEDPUSH")
      settings.javaClass.getMethod("setPreferredNotificationMethod", unifiedPushMethod.javaClass).invoke(settings, unifiedPushMethod)
      account.javaClass.getMethod("setFcmEnabled", Boolean::class.javaPrimitiveType).invoke(account, false)
      unified.javaClass.getMethod("setEnabled", Boolean::class.javaPrimitiveType).invoke(unified, true)
      unified.javaClass.getMethod("setRegistrationStatus", oldStatus.javaClass).invoke(unified, enumValue(target, REGISTRATION_STATUS, "REGISTERED"))
      unified.javaClass.getMethod("setDevice", target.classLoader.loadClass(MOLLY_SOCKET_DEVICE)).invoke(unified, null)
      unified.javaClass.getMethod("setVapidPublicKey", String::class.java).invoke(unified, null)
      unified.javaClass.getMethod("setMollySocketUrl", String::class.java).invoke(unified, null)
      unified.javaClass.getMethod("setAirGapped", Boolean::class.javaPrimitiveType).invoke(unified, false)
      flushSignalStore(target)

      val pushAvailableMethod = account.javaClass.getMethod("isPushAvailable")
      assertThat(account.javaClass.getMethod("getCanReceiveFcm").invoke(account) == false, "temporary FCM-disabled fixture must not be FCM-reachable")
      assertThat(pushAvailableMethod.invoke(account) as Boolean, "registered enabled UnifiedPush fixture should report push available before refresh")
      val jobClass = target.classLoader.loadClass(REFRESH_JOB)
      val job = jobClass.getConstructor().newInstance()
      jobClass.getMethod("setContext", Context::class.java).invoke(job, target)
      jobClass.getMethod("onRun").invoke(job)
      flushSignalStore(target)

      val pending = enumValue(target, REGISTRATION_STATUS, "PENDING")
      assertThat(unified.javaClass.getMethod("getRegistrationStatus").invoke(unified) == pending, "missing-VAPID refresh should move registration to PENDING")
      assertThat(!(pushAvailableMethod.invoke(account) as Boolean), "PENDING UnifiedPush must make push unavailable for this registered account")
      results += "PASS actual UnifiedPushRefreshJob missing-VAPID transition (no endpoint request)"
    } finally {
      settings.javaClass.getMethod("setPreferredNotificationMethod", oldMethod.javaClass).invoke(settings, oldMethod)
      if (!hasMethod) removeStoreKey(settings, METHOD_KEY)
      account.javaClass.getMethod("setFcmEnabled", Boolean::class.javaPrimitiveType).invoke(account, oldFcmEnabled)
      unified.javaClass.getMethod("setEnabled", Boolean::class.javaPrimitiveType).invoke(unified, oldEnabled)
      unified.javaClass.getMethod("setRegistrationStatus", oldStatus.javaClass).invoke(unified, oldStatus)
      unified.javaClass.getMethod("setDevice", target.classLoader.loadClass(MOLLY_SOCKET_DEVICE)).invoke(unified, oldDevice)
      unified.javaClass.getMethod("setVapidPublicKey", String::class.java).invoke(unified, oldVapid)
      unified.javaClass.getMethod("setMollySocketUrl", String::class.java).invoke(unified, oldSocket)
      unified.javaClass.getMethod("setAirGapped", Boolean::class.javaPrimitiveType).invoke(unified, oldAirGapped)
      flushSignalStore(target)
      resetAndStartNetwork(target)
    }
  }

  private fun resetAndStartNetwork(target: Context) {
    val appDependencies = target.classLoader.loadClass("org.thoughtcrime.securesms.dependencies.AppDependencies")
    appDependencies.getMethod("resetNetwork").invoke(null)
    appDependencies.getMethod("startNetwork").invoke(null)
  }

  private fun waitForBenchmarkUnlocked(target: Context) {
    val account = signalValues(target).second
    val getAci = { account.javaClass.getMethod("getAci").invoke(account) }
    val isRegistered = { account.javaClass.getMethod("isRegistered").invoke(account) as Boolean }
    if (getAci() == null || !isRegistered()) {
      // BenchmarkSetupActivity runs TestUsers.setupSelf() and message-send setup. That path
      // creates fixed synthetic credentials locally and blocks Signal network access.
      val setupIntent = Intent().setClassName(target.packageName, "org.signal.benchmark.BenchmarkSetupActivity")
        .putExtra("setup-type", "message-send")
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
      startActivitySync(setupIntent)
      waitUntil("synthetic benchmark account registration", 60_000) { getAci() != null && isRegistered() }
      results += "PASS synthetic benchmark account created locally without a real account or server"
    }
    waitUntil("benchmark app unlocked", 20_000) { !isTargetLocked(target) }
  }

  private fun isTargetLocked(target: Context): Boolean = target.classLoader
    .loadClass("org.thoughtcrime.securesms.service.KeyCachingService")
    .getMethod("isLocked")
    .invoke(null) as Boolean

  private fun waitUntil(label: String, timeoutMs: Long = 5000, predicate: () -> Boolean) {
    val deadline = SystemClock.uptimeMillis() + timeoutMs
    while (SystemClock.uptimeMillis() < deadline) {
      if (predicate()) return
      SystemClock.sleep(100)
    }
    assertThat(predicate(), "$label timed out")
  }

  private fun restoreFixture(target: Context) {
    val probe = testPrefs()
    if (probe.getString(KEY_INSTANCE, null) != null) {
      try {
        target.classLoader.loadClass(UNIFIED_PUSH_API)
          .getMethod("unregisterApp", Context::class.java, String::class.java)
          .invoke(null, target, INSTANCE)
        waitUntil("cleanup UNREGISTERED callback", 2000) {
          unifiedValues(target).javaClass.getMethod("getEndpoint").invoke(unifiedValues(target)) == null
        }
      } catch (_: Throwable) {
        // Continue restoring the captured local state if the fake callback is unavailable.
      }
    }
    val snapshot = probe.getString(KEY_SNAPSHOT, null)
    if (snapshot != null) {
      restorePreferences(target.getSharedPreferences(CONNECTOR_PREFS, Context.MODE_PRIVATE), JSONObject(snapshot))
      val original = probe.getLong(KEY_ORIGINAL_LAST_RECEIVED, 0L)
      val unified = unifiedValues(target)
      unified.javaClass.getMethod("setLastReceivedTime", Long::class.javaPrimitiveType).invoke(unified, original)
      unified.javaClass.getMethod("setEndpoint", String::class.java).invoke(unified, probe.getString(KEY_ORIGINAL_ENDPOINT, null))
      flushSignalStore(target)
      (target.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).cancel(TEST_NOTIFICATION_ID)
      probe.edit().clear().commit()
    }
  }

  private fun snapshotPreferences(prefs: SharedPreferences): JSONObject {
    val snapshot = JSONObject()
    for ((key, value) in prefs.all) {
      val entry = JSONObject()
      when (value) {
        is String -> entry.put("type", "string").put("value", value)
        is Boolean -> entry.put("type", "boolean").put("value", value)
        is Int -> entry.put("type", "int").put("value", value)
        is Long -> entry.put("type", "long").put("value", value)
        is Float -> entry.put("type", "float").put("value", value.toDouble())
        is Set<*> -> entry.put("type", "set").put("value", JSONArray(value.map { it.toString() }))
        else -> throw ProbeFailure("unsupported connector preference type")
      }
      snapshot.put(key, entry)
    }
    return snapshot
  }

  private fun restorePreferences(prefs: SharedPreferences, snapshot: JSONObject) {
    val editor = prefs.edit().clear()
    val keys = snapshot.keys()
    while (keys.hasNext()) {
      val key = keys.next()
      val entry = snapshot.getJSONObject(key)
      when (entry.getString("type")) {
        "string" -> editor.putString(key, entry.getString("value"))
        "boolean" -> editor.putBoolean(key, entry.getBoolean("value"))
        "int" -> editor.putInt(key, entry.getInt("value"))
        "long" -> editor.putLong(key, entry.getLong("value"))
        "float" -> editor.putFloat(key, entry.getDouble("value").toFloat())
        "set" -> {
          val array = entry.getJSONArray("value")
          val values = (0 until array.length()).map { array.getString(it) }.toSet()
          editor.putStringSet(key, values)
        }
        else -> throw ProbeFailure("unsupported saved connector preference type")
      }
    }
    assertThat(editor.commit(), "failed restoring connector preferences")
  }

  private fun assertClip(clipboard: ClipboardManager, label: String, expected: String) {
    val clip = clipboard.primaryClip ?: throw ProbeFailure("clipboard is empty")
    assertThat(clip.description.label.toString() == label, "clipboard label mismatch")
    val text = clip.getItemAt(0).coerceToText(targetContext).toString()
    assertThat(text == expected, "clipboard value mismatch")
  }

  private fun assertSensitiveClipboardMetadata(clipboard: ClipboardManager) {
    if (android.os.Build.VERSION.SDK_INT >= 33) {
      val description = clipboard.primaryClip?.description ?: throw ProbeFailure("clipboard is empty")
      val extras = description.extras
      assertThat(extras?.getBoolean(ClipDescription.EXTRA_IS_SENSITIVE, false) == true, "Android 13+ clipboard item is missing EXTRA_IS_SENSITIVE")
    }
  }

  private fun signalValues(target: Context): Pair<Any, Any> = Pair(
    staticValue(target, SIGNAL_STORE, "settings"),
    staticValue(target, SIGNAL_STORE, "account")
  )

  private fun unifiedValues(target: Context): Any = staticValue(target, SIGNAL_STORE, "unifiedpush")

  private fun staticValue(target: Context, className: String, method: String): Any =
    target.classLoader.loadClass(className).getMethod(method).invoke(null)
      ?: throw ProbeFailure("$method returned null")

  private fun enumValue(target: Context, className: String, name: String): Any {
    val klass = target.classLoader.loadClass(className)
    @Suppress("UNCHECKED_CAST")
    return java.lang.Enum.valueOf(klass as Class<out Enum<*>>, name)
  }

  private fun setFcm(account: Any, value: Boolean) {
    account.javaClass.getMethod("setFcmEnabled", Boolean::class.javaPrimitiveType).invoke(account, value)
  }

  private fun removeStoreKey(settings: Any, key: String) {
    val method = settings.javaClass.superclass.getDeclaredMethod("remove", String::class.java)
    method.isAccessible = true
    method.invoke(settings, key)
  }

  private fun flushSignalStore(target: Context) {
    target.classLoader.loadClass(SIGNAL_STORE).getMethod("blockUntilAllWritesFinished").invoke(null)
  }

  // Instrumentation and target APKs have different UIDs. Keep this disposable
  // checkpoint in a target-owned, uniquely named preferences file so it survives
  // force-stop/restart and can be cleaned up by the runner.
  private fun testPrefs(): SharedPreferences = targetContext.getSharedPreferences(TEST_PREFS, Context.MODE_PRIVATE)

  private fun runCheck(name: String, check: () -> Unit) {
    try {
      check()
      results += "PASS $name"
    } catch (t: Throwable) {
      fail(name, unwrap(t))
    }
  }

  private fun fail(name: String, t: Throwable) {
    failures += "$name: ${t.javaClass.simpleName}: ${t.message ?: "failed"}"
  }

  private fun assertThat(value: Boolean, message: String) {
    if (!value) throw ProbeFailure(message)
  }

  private fun unwrap(t: Throwable): Throwable = when (t) {
    is InvocationTargetException -> t.targetException ?: t
    else -> t
  }

  private class ProbeFailure(message: String) : RuntimeException(message)

  companion object {
    private const val TARGET_PACKAGE = "org.thoughtcrime.securesms.benchmark"
    private const val SIGNAL_STORE = "org.thoughtcrime.securesms.keyvalue.SignalStore"
    private const val DELIVERY_METHOD = "org.thoughtcrime.securesms.keyvalue.SettingsValues\$NotificationDeliveryMethod"
    private const val SETTINGS_VIEW_MODEL = "im.molly.unifiedpush.components.settings.app.notifications.UnifiedPushSettingsViewModel"
    private const val REFRESH_JOB = "org.thoughtcrime.securesms.jobs.UnifiedPushRefreshJob"
    private const val REGISTRATION_STATUS = "im.molly.unifiedpush.model.RegistrationStatus"
    private const val MOLLY_SOCKET_DEVICE = "im.molly.unifiedpush.model.MollySocketDevice"
    private const val UNIFIED_PUSH_API = "org.unifiedpush.android.connector.UnifiedPush"
    private const val CONNECTOR_PREFS = "unifiedpush.connector"
    private const val RECEIVER = "im.molly.unifiedpush.receiver.UnifiedPushReceiver"
    private const val ACTION_FAKE_MESSAGE = "org.example.upfake.TEST_MESSAGE"
    private const val ACTION_FAKE_UNREGISTERED = "org.example.upfake.TEST_UNREGISTERED"
    private const val FAKE_DISTRIBUTOR = "org.example.upfake"
    private const val FAKE_ENDPOINT = "https://127.0.0.1/up-test-endpoint"
    private const val INSTANCE = "default"
    private const val TEST_NOTIFICATION_ID = 51216
    private const val METHOD_KEY = "molly.notificationMethod"
    private const val TEST_PREFS = "p2_instrumentation_state"
    private const val KEY_SNAPSHOT = "connectorSnapshot"
    private const val KEY_INSTANCE = "instance"
    private const val KEY_ORIGINAL_LAST_RECEIVED = "originalLastReceived"
    private const val KEY_SEED_RECEIVED_TIME = "seedReceivedTime"
    private const val KEY_ORIGINAL_ENDPOINT = "originalEndpoint"
  }
}
