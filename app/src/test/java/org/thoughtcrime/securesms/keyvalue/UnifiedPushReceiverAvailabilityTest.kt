package org.thoughtcrime.securesms.keyvalue

import android.app.Application
import android.content.Intent
import androidx.test.core.app.ApplicationProvider
import im.molly.unifiedpush.model.MollySocketDevice
import im.molly.unifiedpush.model.RegistrationStatus
import im.molly.unifiedpush.receiver.UnifiedPushReceiver
import io.mockk.every
import io.mockk.just
import io.mockk.mockkObject
import io.mockk.mockkStatic
import io.mockk.Runs
import io.mockk.spyk
import io.mockk.clearMocks
import io.mockk.unmockkAll
import io.mockk.verify
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.thoughtcrime.securesms.dependencies.AppDependencies
import org.thoughtcrime.securesms.gcm.FcmFetchManager
import org.thoughtcrime.securesms.service.KeyCachingService
import org.thoughtcrime.securesms.util.TextSecurePreferences
import org.unifiedpush.android.connector.FailedReason
import org.unifiedpush.android.connector.UnifiedPush
import org.unifiedpush.android.connector.data.PushMessage
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class, manifest = Config.NONE)
class UnifiedPushReceiverAvailabilityTest {
  private lateinit var context: Application
  private lateinit var storage: MemoryKeyValueStorage
  private lateinit var store: KeyValueStore
  private lateinit var values: UnifiedPushValues
  private lateinit var account: AccountValues

  @Before
  fun setUp() {
    context = ApplicationProvider.getApplicationContext()
    storage = MemoryKeyValueStorage()
    store = KeyValueStore(storage)
    values = spyk(UnifiedPushValues(store))
    account = AccountValues(store, context)
    mockkStatic(SignalStore::class)
    every { SignalStore.unifiedpush } returns values
    mockkStatic(KeyCachingService::class)
    every { KeyCachingService.isLocked() } returns true
    mockkObject(AppDependencies)
    every { AppDependencies.resetNetwork() } just Runs
    every { AppDependencies.startNetwork() } just Runs
    mockkObject(UnifiedPush)
    every { UnifiedPush.forceRemoveDistributor(any()) } just Runs
    mockkObject(FcmFetchManager)
    every { FcmFetchManager.postMayHaveMessagesNotificationForLockedPush(any()) } just Runs
  }

  @After
  fun tearDown() {
    unmockkAll()
  }

  @Test
  fun `locked endpoint rotation invalidates availability without changing protected endpoint`() {
    seedRegisteredState()
    storage.startRecording()
    clearMocks(values, answers = false, recordedCalls = true)

    UnifiedPushReceiver().onNewEndpoint(context, io.mockk.mockk(relaxed = true), "instance")
    storage.awaitWrite()

    assertNoProtectedReads()
    assertFalse(values.isAvailableOrAirGapped)
    assertFalse(account.pushAvailable)
    assertEquals("old-endpoint", values.endpoint)
    assertEquals(MollySocketDevice(17, "fixture-password"), values.device)
    assertEquals(listOf("mollysocket.status"), storage.writes)
    verify(exactly = 1) { AppDependencies.resetNetwork() }
    verify(exactly = 1) { AppDependencies.startNetwork() }
  }

  @Test
  fun `locked distributor removal invalidates availability and preserves device credentials`() {
    seedRegisteredState()
    storage.startRecording()
    clearMocks(values, answers = false, recordedCalls = true)

    UnifiedPushReceiver().onUnregistered(context, "instance")
    storage.awaitWrite()

    assertNoProtectedReads()
    assertFalse(values.isAvailableOrAirGapped)
    assertFalse(account.pushAvailable)
    assertEquals("old-endpoint", values.endpoint)
    assertEquals(MollySocketDevice(17, "fixture-password"), values.device)
    assertEquals(listOf("mollysocket.status"), storage.writes)
    verify(exactly = 1) { UnifiedPush.forceRemoveDistributor(context) }
    verify(exactly = 1) { AppDependencies.resetNetwork() }
    verify(exactly = 1) { AppDependencies.startNetwork() }
  }

  @Test
  fun `locked registration failure invalidates stale registered state`() {
    seedRegisteredState()
    storage.startRecording()
    clearMocks(values, answers = false, recordedCalls = true)

    UnifiedPushReceiver().onRegistrationFailed(context, FailedReason.NETWORK, "instance")
    storage.awaitWrite()

    assertNoProtectedReads()
    assertFalse(values.isAvailableOrAirGapped)
    assertFalse(account.pushAvailable)
    assertEquals(MollySocketDevice(17, "fixture-password"), values.device)
    assertEquals(listOf("mollysocket.status"), storage.writes)
    verify(exactly = 1) { AppDependencies.resetNetwork() }
    verify(exactly = 1) { AppDependencies.startNetwork() }
  }

  @Test
  fun `unlocked unregister invalidates registered state when endpoint is already absent`() {
    seedRegisteredState()
    values.endpoint = null
    store.blockUntilAllWritesFinished()
    storage.startRecording()
    every { KeyCachingService.isLocked() } returns false
    clearMocks(values, answers = false, recordedCalls = true)

    UnifiedPushReceiver().onUnregistered(context, "instance")
    storage.awaitWrite()

    assertNoProtectedReads(checkEndpoint = false)
    assertFalse(values.isAvailableOrAirGapped)
    assertFalse(account.pushAvailable)
    assertEquals(listOf("mollysocket.status"), storage.writes)
    verify(exactly = 1) { UnifiedPush.forceRemoveDistributor(context) }
    verify(exactly = 1) { AppDependencies.resetNetwork() }
    verify(exactly = 1) { AppDependencies.startNetwork() }
  }

  @Test
  fun `locked urgent message only posts the generic notice when enabled`() {
    TextSecurePreferences.setPassphraseLockNotificationsEnabled(context, false)
    val receiver = UnifiedPushReceiver()
    val message = PushMessage("{\"urgent\":true,\"body\":\"secret fixture\"}".toByteArray(), true)

    receiver.onMessage(context, message, "instance")
    verify(exactly = 0) { FcmFetchManager.postMayHaveMessagesNotificationForLockedPush(any()) }

    TextSecurePreferences.setPassphraseLockNotificationsEnabled(context, true)
    receiver.onMessage(context, message, "instance")
    verify(exactly = 1) { FcmFetchManager.postMayHaveMessagesNotificationForLockedPush(context) }
  }

  @Test
  fun `locked malformed and test payloads do not trigger notifications or content fetch`() {
    TextSecurePreferences.setPassphraseLockNotificationsEnabled(context, true)
    val receiver = UnifiedPushReceiver()

    receiver.onMessage(context, PushMessage("not-json".toByteArray(), true), "instance")
    receiver.onMessage(context, PushMessage("{\"test\":true}".toByteArray(), true), "instance")

    verify(exactly = 0) { FcmFetchManager.postMayHaveMessagesNotificationForLockedPush(any()) }
    verify(exactly = 0) { AppDependencies.resetNetwork() }
    verify(exactly = 0) { AppDependencies.startNetwork() }
  }

  @Test
  fun `connector rejects missing and unknown registration tokens before callback dispatch`() {
    seedRegisteredState()
    val receiver = UnifiedPushReceiver()

    receiver.onReceive(context, Intent("org.unifiedpush.android.connector.UNREGISTERED"))
    receiver.onReceive(
      context,
      Intent("org.unifiedpush.android.connector.UNREGISTERED").putExtra("token", "unknown-token")
    )

    assertTrue(account.pushAvailable)
    assertEquals(RegistrationStatus.REGISTERED, values.registrationStatus)
    verify(exactly = 0) { UnifiedPush.forceRemoveDistributor(any()) }
    verify(exactly = 0) { AppDependencies.resetNetwork() }
    verify(exactly = 0) { AppDependencies.startNetwork() }
  }

  private fun seedRegisteredState() {
    values.enabled = true
    values.registrationStatus = RegistrationStatus.REGISTERED
    values.endpoint = "old-endpoint"
    values.device = MollySocketDevice(17, "fixture-password")
    assertTrue(values.isAvailableOrAirGapped)
    assertTrue(account.pushAvailable)
    store.blockUntilAllWritesFinished()
    storage.writes.clear()
  }

  private fun assertNoProtectedReads(checkEndpoint: Boolean = true) {
    if (checkEndpoint) {
      verify(exactly = 0) { values.endpoint }
    }
    verify(exactly = 0) { values.device }
    verify(exactly = 0) { values.mollySocketUrl }
    verify(exactly = 0) { values.vapidPublicKey }
  }

  private class MemoryKeyValueStorage : KeyValuePersistentStorage {
    private val data = KeyValueDataSet()
    val writes = mutableListOf<String>()
    private var writeLatch = CountDownLatch(0)

    override fun getDataSet(): KeyValueDataSet = KeyValueDataSet().also { it.putAll(data) }

    override fun writeDataSet(dataSet: KeyValueDataSet, removes: Collection<String>) {
      synchronized(writes) {
        writes += listOf("mollysocket.status", "up.endpoint", "mollysocket.deviceId", "mollysocket.passwd")
          .filter(dataSet::containsKey)
      }
      data.putAll(dataSet)
      data.removeAll(removes)
      writeLatch.countDown()
    }

    fun startRecording() {
      writes.clear()
      writeLatch = CountDownLatch(1)
    }

    fun awaitWrite() {
      check(writeLatch.await(5, TimeUnit.SECONDS)) { "Timed out waiting for key-value write" }
    }
  }
}
