package de.rnfulda.app

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Bitmap
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Bundle
import android.view.View
import android.webkit.*
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.net.toUri
import de.rnfulda.app.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val appUrl = "https://fuldasozial.de"
    private val appHost = "fuldasozial.de"

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        webViewEinrichten()

        // Modern Back Button Handling
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (binding.webView.canGoBack()) {
                    binding.webView.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })

        // Pull-to-Refresh
        binding.swipeRefresh.setColorSchemeColors(getColor(R.color.rot))
        binding.swipeRefresh.setOnRefreshListener {
            binding.webView.reload()
        }

        // Erneut versuchen (Offline-Ansicht)
        binding.btnErneut.setOnClickListener { seiteLaden() }

        // Gespeicherten Zustand wiederherstellen oder Seite laden
        if (savedInstanceState != null) {
            binding.webView.restoreState(savedInstanceState)
        } else {
            seiteLaden()
        }
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
            // Hardware-Beschleunigung für flüssiges Scrollen auf S21
            domStorageEnabled = true
            databaseEnabled = true
            // Cache nutzen wenn offline
            cacheMode = WebSettings.LOAD_DEFAULT
            // Sicherheit: kein Mixed Content
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            // User-Agent: App kenntlich machen (für zukünftige App-spezifische Features)
            userAgentString = "$userAgentString RNFuldaApp/1.0"
        }

        binding.webView.webViewClient = object : WebViewClient() {

            override fun shouldOverrideUrlLoading(
                view: WebView,
                request: WebResourceRequest
            ): Boolean {
                val url = request.url.toString()
                val host = request.url.host ?: ""

                return when {
                    // Eigene Domain → im WebView öffnen
                    host.endsWith(appHost) -> false
                    // Ko-fi, externe Links → im System-Browser öffnen
                    url.startsWith("http") -> {
                        startActivity(Intent(Intent.ACTION_VIEW, url.toUri()))
                        true
                    }
                    // mailto:, tel: etc.
                    else -> {
                        runCatching { startActivity(Intent(Intent.ACTION_VIEW, url.toUri())) }
                        true
                    }
                }
            }

            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                binding.progressBar.visibility = View.VISIBLE
                binding.offlineView.visibility = View.GONE
                binding.webView.visibility = View.VISIBLE
            }

            override fun onPageFinished(view: WebView, url: String) {
                binding.progressBar.visibility = View.GONE
                binding.swipeRefresh.isRefreshing = false
            }

            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: WebResourceError
            ) {
                if (request.isForMainFrame) {
                    binding.progressBar.visibility = View.GONE
                    binding.webView.visibility = View.GONE
                    binding.offlineView.visibility = View.VISIBLE
                    binding.swipeRefresh.isRefreshing = false
                }
            }
        }

        binding.webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, newProgress: Int) {
                binding.progressBar.progress = newProgress
                if (newProgress == 100) {
                    binding.progressBar.visibility = View.GONE
                }
            }
        }
    }

    private fun seiteLaden() {
        if (hatInternet()) {
            binding.offlineView.visibility = View.GONE
            binding.webView.visibility = View.VISIBLE
            binding.webView.loadUrl(appUrl)
        } else {
            binding.offlineView.visibility = View.VISIBLE
            binding.webView.visibility = View.GONE
            binding.progressBar.visibility = View.GONE
        }
    }

    private fun hatInternet(): Boolean {
        val cm = getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        binding.webView.saveState(outState)
    }
}
