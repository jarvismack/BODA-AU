package com.bodaboda.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.Context
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.webkit.CookieManager
import android.webkit.GeolocationPermissions
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import com.bodaboda.app.BuildConfig
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import java.util.Timer
import java.util.TimerTask

class MainActivity : Activity() {
    private lateinit var webView: WebView
    private var lastUrl: String? = null
    private val prefs by lazy { getSharedPreferences("bodaau_prefs", MODE_PRIVATE) }
    private val notifPermissionRequest = 1001
    private val locationPermissionRequest = 1002
    private val notificationChannelId = "bodaau_notifications"
    private val notificationPollIntervalMs = 60_000L
    private val pushRegistrationIntervalMs = 5 * 60_000L
    private var notificationTimer: Timer? = null
    private var pushRegistrationTimer: Timer? = null
    private var appVisible = false
    private var lastNativeNotificationId = 0
    private var pushInstallationId: String? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        setTheme(R.style.Theme_BodaAU)
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        requestNotificationPermission()
        requestLocationPermission()
        createNotificationChannel()
        loadLastNativeNotificationId()
        loadPushInstallationId()

        webView = findViewById(R.id.webview)
        configureWebView()
        webView.addJavascriptInterface(PushBridge(), "BodaPushBridge")

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val targetUri = request?.url ?: return false
                val url = targetUri.toString()
                if (url == "app://retry") {
                    loadBaseUrl()
                    return true
                }
                if (!isSupportedInWebView(targetUri)) {
                    return openExternal(targetUri)
                }
                lastUrl = url
                return false
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                if (request?.isForMainFrame == true) {
                    showOffline()
                }
            }
        }
        webView.webChromeClient = object : WebChromeClient() {
            override fun onGeolocationPermissionsShowPrompt(
                origin: String?,
                callback: GeolocationPermissions.Callback?
            ) {
                callback?.invoke(origin, true, false)
            }
        }

        if (isOnline()) {
            loadBaseUrl()
        } else {
            showOffline()
        }

        startNativeNotificationPolling()
        startPushRegistrationPolling()
        checkForUpdate()
    }

    override fun onResume() {
        super.onResume()
        appVisible = true
        registerPushTokenIfPossible()
    }

    override fun onPause() {
        appVisible = false
        super.onPause()
    }

    override fun onDestroy() {
        notificationTimer?.cancel()
        notificationTimer = null
        pushRegistrationTimer?.cancel()
        pushRegistrationTimer = null
        if (::webView.isInitialized) {
            webView.removeJavascriptInterface("BodaPushBridge")
            webView.stopLoading()
            webView.webViewClient = WebViewClient()
            webView.webChromeClient = null
            webView.destroy()
        }
        super.onDestroy()
    }

    private fun configureWebView() {
        CookieManager.getInstance().setAcceptCookie(true)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)
            webView.settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            webView.settings.safeBrowsingEnabled = true
        }

        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.databaseEnabled = true
        webView.settings.allowFileAccess = false
        webView.settings.allowContentAccess = false
        webView.settings.cacheMode = WebSettings.LOAD_DEFAULT
        webView.settings.loadsImagesAutomatically = true
        webView.settings.mediaPlaybackRequiresUserGesture = false
        webView.settings.userAgentString =
            "${webView.settings.userAgentString} BodaAU/${BuildConfig.VERSION_NAME}"
    }

    private fun loadBaseUrl() {
        val baseUrl = getString(R.string.base_url).trim()
        if (baseUrl.isBlank()) {
            showOffline()
            return
        }
        lastUrl = baseUrl
        webView.loadUrl(baseUrl)
    }

    private fun showOffline() {
        webView.loadUrl("file:///android_asset/offline.html")
    }

    private fun isSupportedInWebView(uri: Uri): Boolean {
        val scheme = uri.scheme?.lowercase() ?: return false
        return scheme == "http" || scheme == "https"
    }

    private fun openExternal(uri: Uri): Boolean {
        return try {
            val externalIntent = when (uri.scheme?.lowercase()) {
                "intent" -> Intent.parseUri(uri.toString(), Intent.URI_INTENT_SCHEME)
                else -> Intent(Intent.ACTION_VIEW, uri)
            }.apply {
                addCategory(Intent.CATEGORY_BROWSABLE)
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }

            if (externalIntent.resolveActivity(packageManager) == null) {
                if (uri.scheme?.equals("intent", ignoreCase = true) == true) {
                    val fallbackUrl = externalIntent.getStringExtra("browser_fallback_url")
                    if (!fallbackUrl.isNullOrBlank()) {
                        webView.loadUrl(fallbackUrl)
                        return true
                    }
                }
                startActivity(Intent(Settings.ACTION_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                return true
            }

            startActivity(externalIntent)
            true
        } catch (_: Exception) {
            false
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            notificationChannelId,
            "BODA AU Updates",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "Ride, account and system alerts from BODA AU"
        }
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(channel)
    }

    private fun loadLastNativeNotificationId() {
        lastNativeNotificationId = prefs.getInt("last_native_notification_id", 0)
    }

    private fun loadPushInstallationId() {
        val stored = prefs.getString("push_installation_id", null)
        if (!stored.isNullOrBlank()) {
            pushInstallationId = stored
            return
        }
        val generated = UUID.randomUUID().toString()
        pushInstallationId = generated
        prefs.edit().putString("push_installation_id", generated).apply()
    }

    private fun saveLastNativeNotificationId(value: Int) {
        lastNativeNotificationId = value
        prefs.edit().putInt("last_native_notification_id", value).apply()
    }

    private fun startNativeNotificationPolling() {
        if (notificationTimer != null) return
        notificationTimer = Timer("bodaau-native-notifications", true).apply {
            scheduleAtFixedRate(object : TimerTask() {
                override fun run() {
                    pollNativeNotifications()
                }
            }, 15_000L, notificationPollIntervalMs)
        }
    }

    private fun startPushRegistrationPolling() {
        if (pushRegistrationTimer != null) return
        pushRegistrationTimer = Timer("bodaau-push-registration", true).apply {
            scheduleAtFixedRate(object : TimerTask() {
                override fun run() {
                    registerPushTokenIfPossible()
                }
            }, 20_000L, pushRegistrationIntervalMs)
        }
    }

    private fun registerPushTokenIfPossible() {
        Thread {
            try {
                val baseUrl = getString(R.string.base_url).trimEnd('/')
                val cookie = CookieManager.getInstance().getCookie(baseUrl)
                if (cookie.isNullOrBlank()) return@Thread

                val token = pushInstallationId?.trim().orEmpty()
                if (token.length < 16) return@Thread

                val url = URL("$baseUrl/api/push/tokens/register/")
                val payload = JSONObject().apply {
                    put("device_token", token)
                    put("platform", "android")
                    put("device_id", token)
                    put("is_active", true)
                }

                val conn = (url.openConnection() as HttpURLConnection).apply {
                    connectTimeout = 4000
                    readTimeout = 4000
                    requestMethod = "POST"
                    doOutput = true
                    setRequestProperty("Accept", "application/json")
                    setRequestProperty("Content-Type", "application/json")
                    setRequestProperty("Cookie", cookie)
                }

                conn.outputStream.use { stream ->
                    OutputStreamWriter(stream, Charsets.UTF_8).use { writer ->
                        writer.write(payload.toString())
                        writer.flush()
                    }
                }

                if (conn.responseCode !in 200..299) return@Thread

                conn.inputStream.bufferedReader().use { it.readText() }
                getSharedPreferences("bodaau_prefs", MODE_PRIVATE)
                    .edit()
                    .putLong("push_token_last_synced_at", System.currentTimeMillis())
                    .apply()
            } catch (_: Exception) {
                // Best-effort registration; retry on the next timer tick.
            }
        }.start()
    }

    private fun pollNativeNotifications() {
        Thread {
            try {
                val baseUrl = getString(R.string.base_url).trimEnd('/')
                val cookie = CookieManager.getInstance().getCookie(baseUrl)
                if (cookie.isNullOrBlank()) return@Thread

                val url = URL("$baseUrl/api/notifications/")
                val conn = (url.openConnection() as HttpURLConnection).apply {
                    connectTimeout = 4000
                    readTimeout = 4000
                    setRequestProperty("Accept", "application/json")
                    setRequestProperty("Cookie", cookie)
                }
                if (conn.responseCode != 200) return@Thread

                val body = conn.inputStream.bufferedReader().use { it.readText() }
                val json = JSONObject(body)
                val notifications = json.optJSONArray("notifications") ?: return@Thread
                var maxSeenId = lastNativeNotificationId
                val pendingNotifications = mutableListOf<JSONObject>()

                for (i in 0 until notifications.length()) {
                    val item = notifications.optJSONObject(i) ?: continue
                    val id = item.optInt("id", 0)
                    if (id <= lastNativeNotificationId) continue
                    if (!item.optBoolean("is_read", false)) {
                        pendingNotifications.add(item)
                    }
                    if (id > maxSeenId) {
                        maxSeenId = id
                    }
                }

                if (maxSeenId > lastNativeNotificationId) {
                    saveLastNativeNotificationId(maxSeenId)
                }

                if (appVisible || pendingNotifications.isEmpty()) return@Thread

                pendingNotifications.sortBy { it.optInt("id", 0) }
                pendingNotifications.forEach { notification ->
                    showNativeNotification(
                        notification.optInt("id", 0),
                        notification.optString("title", "BODA AU"),
                        notification.optString("message", "You have a new alert.")
                    )
                }
            } catch (_: Exception) {
                // Native notifications are best-effort only.
            }
        }.start()
    }

    private fun showNativeNotification(notificationId: Int, title: String, message: String) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                return
            }
        }

        if (notificationId <= 0) return

        val openIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this,
            notificationId,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, notificationChannelId)
        } else {
            Notification.Builder(this)
        }

        val notification = builder
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(message)
            .setStyle(Notification.BigTextStyle().bigText(message))
            .setPriority(Notification.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .build()

        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(notificationId, notification)
    }

    private fun isOnline(): Boolean {
        val cm = getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return false
        val capabilities = cm.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), notifPermissionRequest)
            }
        }
    }

    private fun requestLocationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val fine = checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
            val coarse = checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
            if (!fine && !coarse) {
                requestPermissions(
                    arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION),
                    locationPermissionRequest
                )
            }
        }
    }

    inner class PushBridge {
        @JavascriptInterface
        fun refreshPushRegistration() {
            registerPushTokenIfPossible()
        }
    }

    private fun checkForUpdate() {
        Thread {
            try {
                val baseUrl = getString(R.string.base_url).trimEnd('/')
                val url = URL("$baseUrl/app/version.json")
                val conn = (url.openConnection() as HttpURLConnection).apply {
                    connectTimeout = 4000
                    readTimeout = 4000
                }
                if (conn.responseCode == 200) {
                    val body = conn.inputStream.bufferedReader().use { it.readText() }
                    val json = JSONObject(body)
                    val latestCode = json.optInt("versionCode", 0)
                    val apkUrl = json.optString("apkUrl", "")
                    val versionName = json.optString("versionName", "")
                    val installedCode = BuildConfig.VERSION_CODE
                    val ignoredVersion = prefs.getInt("ignored_version", 0)
                    val lastPromptedVersion = prefs.getInt("last_prompted_version", 0)
                    if (latestCode <= installedCode) {
                        if (ignoredVersion != 0 || lastPromptedVersion != 0) {
                            prefs.edit()
                                .remove("ignored_version")
                                .remove("last_prompted_version")
                                .apply()
                        }
                        return@Thread
                    }
                    if (latestCode > ignoredVersion && latestCode != lastPromptedVersion && apkUrl.isNotBlank()) {
                        runOnUiThread { showUpdateDialog(apkUrl, versionName, latestCode) }
                    }
                }
            } catch (_: Exception) {
                // Silent fail: update check is best-effort only
            }
        }.start()
    }

    private fun showUpdateDialog(apkUrl: String, versionName: String, latestCode: Int) {
        val title = if (versionName.isNotBlank()) {
            "Update available ($versionName)"
        } else {
            "Update available"
        }
        AlertDialog.Builder(this)
            .setTitle(title)
            .setMessage("A new version of BODA AU is available. Please update for the best experience.")
            .setPositiveButton("Update") { _, _ ->
                prefs.edit().putInt("last_prompted_version", latestCode).apply()
                openExternal(Uri.parse(apkUrl))
            }
            .setNegativeButton("Not now") { _, _ ->
                prefs.edit()
                    .putInt("ignored_version", latestCode)
                    .putInt("last_prompted_version", latestCode)
                    .apply()
            }
            .show()
    }

    override fun onBackPressed() {
        if (::webView.isInitialized && webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }
}
