package com.carriez.flutter_hbb

import android.app.Application
import android.system.Os
import android.util.Log
import ffi.FFI

class MainApplication : Application() {
    internal val documentStorage by lazy { DocumentStorage(this) }

    @androidx.annotation.Keep
    fun rustDocumentStorage(request: String): String = documentStorage.request(request)

    companion object {
        private const val TAG = "MainApplication"
    }

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "App start")
        // Initialize before Rust starts, including background service launches.
        Os.setenv("RUSTDESK_ANDROID_NATIVE_LIB_DIR", applicationInfo.nativeLibraryDir, true)
        Os.setenv("RUSTDESK_ANDROID_CACHE_DIR", cacheDir.absolutePath, true)
        FFI.onAppStart(applicationContext)
    }
}
