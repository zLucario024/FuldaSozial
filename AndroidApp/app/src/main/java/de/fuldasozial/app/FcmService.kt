package de.rnfulda.app

import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

class FcmService : FirebaseMessagingService() {

    override fun onNewToken(token: String) {
        val prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
        prefs.edit().putString(KEY_TOKEN, token).apply()
        val heimat = prefs.getString(KEY_HEIMAT, null) ?: return
        CoroutineScope(Dispatchers.IO).launch { apiRegistrieren(token, heimat) }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val title = message.notification?.title ?: message.data["title"] ?: return
        val body  = message.notification?.body  ?: message.data["body"]  ?: ""
        val url   = message.data["url"] ?: ""
        val tag   = message.data["tag"] ?: title

        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(MainActivity.EXTRA_URL, url)
        }
        val pi = PendingIntent.getActivity(
            this, tag.hashCode(), intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setAutoCancel(true)
            .setContentIntent(pi)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()

        (getSystemService(NOTIFICATION_SERVICE) as NotificationManager)
            .notify(tag.hashCode(), notification)
    }

    companion object {
        const val CHANNEL_ID  = "rnfulda_news"
        const val PREFS       = "rnfulda"
        const val KEY_TOKEN   = "fcm_token"
        const val KEY_HEIMAT  = "heimat"
        private const val API = "https://fuldasozial.onrender.com"

        fun apiRegistrieren(token: String, heimat: String) = apiAnfrage(
            "POST", """{"fcm_token":"$token","heimat":"$heimat"}"""
        )

        fun apiHeimatAktualisieren(token: String, heimat: String) = apiAnfrage(
            "PATCH", """{"fcm_token":"$token","heimat":"$heimat"}"""
        )

        fun apiAbmelden(token: String, heimat: String) = apiAnfrage(
            "DELETE", """{"fcm_token":"$token","heimat":"$heimat"}"""
        )

        private fun apiAnfrage(method: String, body: String) {
            try {
                val conn = URL("$API/fcm-abonnieren").openConnection() as HttpURLConnection
                conn.requestMethod = method
                conn.setRequestProperty("Content-Type", "application/json")
                conn.doOutput = true
                OutputStreamWriter(conn.outputStream).use { it.write(body) }
                conn.responseCode
                conn.disconnect()
            } catch (_: Exception) {}
        }
    }
}
