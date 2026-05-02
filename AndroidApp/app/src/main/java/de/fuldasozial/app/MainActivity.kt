package de.rnfulda.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import android.os.Bundle
import android.view.View
import android.webkit.*
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.net.toUri
import com.google.firebase.messaging.FirebaseMessaging
import de.rnfulda.app.BuildConfig
import de.rnfulda.app.databinding.ActivityMainBinding
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val appUrl  = "https://www.rnfulda.de"
    private val appHost = "rnfulda.de"

    private val notifPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) fcmToken()
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        kanalErstellen()
        webViewEinrichten()

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (binding.webView.canGoBack()) binding.webView.goBack()
                else { isEnabled = false; onBackPressedDispatcher.onBackPressed() }
            }
        })

        binding.swipeRefresh.setColorSchemeColors(getColor(R.color.rot))
        binding.swipeRefresh.setOnRefreshListener { binding.webView.reload() }
        binding.btnErneut.setOnClickListener { seiteLaden() }

        if (savedInstanceState != null) {
            binding.webView.restoreState(savedInstanceState)
        } else {
            // Notification tap: load article URL directly
            val url = intent.getStringExtra(EXTRA_URL)
            if (!url.isNullOrBlank()) binding.webView.loadUrl(url)
            else seiteLaden()
        }

        benachrichtigungEinrichten()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        val url = intent.getStringExtra(EXTRA_URL)
        if (!url.isNullOrBlank()) binding.webView.loadUrl(url)
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun webViewEinrichten() {
        with(binding.webView.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            loadWithOverviewMode = true
            useWideViewPort = true
            setSupportZoom(false)
            builtInZoomControls = false
            displayZoomControls = false
            databaseEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            userAgentString = "$userAgentString RNFuldaApp/${BuildConfig.VERSION_NAME}"
        }

        // JavaScript interface so the website can push the selected Heimat to the app
        binding.webView.addJavascriptInterface(AndroidBridge(), "Android")

        binding.webView.webViewClient = object : WebViewClient() {

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url  = request.url.toString()
                val host = request.url.host ?: ""
                return when {
                    host.endsWith(appHost) -> false
                    url.startsWith("http") -> { startActivity(Intent(Intent.ACTION_VIEW, url.toUri())); true }
                    else -> { runCatching { startActivity(Intent(Intent.ACTION_VIEW, url.toUri())) }; true }
                }
            }

            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                binding.progressBar.visibility = View.VISIBLE
                binding.offlineView.visibility = View.GONE
                binding.webView.visibility     = View.VISIBLE
            }

            override fun onPageFinished(view: WebView, url: String) {
                binding.progressBar.visibility  = View.GONE
                binding.swipeRefresh.isRefreshing = false
                // Read Heimat from localStorage in case the JS interface hasn't fired yet
                binding.webView.evaluateJavascript("localStorage.getItem('meineHeimat')") { value ->
                    val heimat = value?.trim('"') ?: return@evaluateJavascript
                    if (heimat != "null" && heimat.isNotBlank()) heimatSpeichern(heimat)
                }
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) {
                    binding.progressBar.visibility = View.GONE
                    binding.webView.visibility     = View.GONE
                    binding.offlineView.visibility = View.VISIBLE
                    binding.swipeRefresh.isRefreshing = false
                }
            }
        }

        binding.webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, newProgress: Int) {
                binding.progressBar.progress = newProgress
                if (newProgress == 100) binding.progressBar.visibility = View.GONE
            }
        }
    }

    inner class AndroidBridge {
        @JavascriptInterface
        fun setHeimat(ort: String) {
            heimatSpeichern(ort)
        }

        @JavascriptInterface
        fun toggleBenachrichtigungen() {
            val prefs  = getSharedPreferences(FcmService.PREFS, MODE_PRIVATE)
            val aktiv  = prefs.getBoolean(KEY_NOTIF_ENABLED, false)
            val token  = prefs.getString(FcmService.KEY_TOKEN, null) ?: return
            val heimat = prefs.getString(FcmService.KEY_HEIMAT, null) ?: return
            prefs.edit().putBoolean(KEY_NOTIF_ENABLED, !aktiv).apply()
            CoroutineScope(Dispatchers.IO).launch {
                if (aktiv) FcmService.apiAbmelden(token, heimat)
                else       FcmService.apiRegistrieren(token, heimat)
            }
        }

        @JavascriptInterface
        fun istBenachrichtigungenAktiv(): Boolean =
            getSharedPreferences(FcmService.PREFS, MODE_PRIVATE)
                .getBoolean(KEY_NOTIF_ENABLED, false)
    }

    private fun heimatSpeichern(heimat: String) {
        val prefs = getSharedPreferences(FcmService.PREFS, MODE_PRIVATE)
        val gespeichert = prefs.getString(FcmService.KEY_HEIMAT, null)
        prefs.edit().putString(FcmService.KEY_HEIMAT, heimat).apply()
        if (!prefs.getBoolean(KEY_NOTIF_ENABLED, false)) return
        val token = prefs.getString(FcmService.KEY_TOKEN, null) ?: return
        CoroutineScope(Dispatchers.IO).launch {
            if (gespeichert != heimat) FcmService.apiHeimatAktualisieren(token, heimat)
        }
    }

    private fun benachrichtigungEinrichten() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            when {
                ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                    == PackageManager.PERMISSION_GRANTED -> fcmToken()
                else -> notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        } else {
            fcmToken()
        }
    }

    private fun fcmToken() {
        FirebaseMessaging.getInstance().token.addOnSuccessListener { token ->
            val prefs = getSharedPreferences(FcmService.PREFS, MODE_PRIVATE)
            prefs.edit().putString(FcmService.KEY_TOKEN, token).apply()
            // Only re-register if user had previously opted in
            if (!prefs.getBoolean(KEY_NOTIF_ENABLED, false)) return@addOnSuccessListener
            val heimat = prefs.getString(FcmService.KEY_HEIMAT, null) ?: return@addOnSuccessListener
            CoroutineScope(Dispatchers.IO).launch { FcmService.apiRegistrieren(token, heimat) }
        }
    }

    private fun kanalErstellen() {
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        if (manager.getNotificationChannel(FcmService.CHANNEL_ID) == null) {
            val channel = NotificationChannel(
                FcmService.CHANNEL_ID,
                "RegioNachrichten Fulda",
                NotificationManager.IMPORTANCE_HIGH
            ).apply { description = "Neue Artikel aus deiner Heimatgemeinde" }
            manager.createNotificationChannel(channel)
        }
    }

    private fun seiteLaden() {
        if (hatInternet()) {
            binding.offlineView.visibility = View.GONE
            binding.webView.visibility     = View.VISIBLE
            binding.webView.loadUrl(appUrl)
        } else {
            binding.offlineView.visibility = View.VISIBLE
            binding.webView.visibility     = View.GONE
            binding.progressBar.visibility = View.GONE
        }
    }

    private fun hatInternet(): Boolean {
        val cm      = getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return false
        val caps    = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        binding.webView.saveState(outState)
    }

    override fun onDestroy() {
        binding.webView.stopLoading()
        binding.webView.removeAllViews()
        binding.webView.destroy()
        super.onDestroy()
    }

    companion object {
        const val EXTRA_URL        = "url"
        const val KEY_NOTIF_ENABLED = "notif_enabled"
    }
}
