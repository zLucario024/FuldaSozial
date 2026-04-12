# WebView JavaScript Interface schützen
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}

# Kotlin Coroutines
-keepclassmembernames class kotlinx.** {
    volatile <fields>;
}
