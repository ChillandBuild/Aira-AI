package com.aira.sync

import android.content.Context
import android.content.SharedPreferences

class Prefs(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("aira_sync_prefs", Context.MODE_PRIVATE)

    var serverUrl: String
        get() = prefs.getString("server_url", "https://api.aira.ai") ?: "https://api.aira.ai"
        set(value) = prefs.edit().putString("server_url", value).apply()

    var syncToken: String
        get() = prefs.getString("sync_token", "") ?: ""
        set(value) = prefs.edit().putString("sync_token", value).apply()

    var lastSyncedTimestampMs: Long
        get() = prefs.getLong("last_synced_timestamp_ms", 0L)
        set(value) = prefs.edit().putLong("last_synced_timestamp_ms", value).apply()

    /** Newest published build seen in version.json (0 = never checked). */
    var latestVersionCode: Long
        get() = prefs.getLong("latest_version_code", 0L)
        set(value) = prefs.edit().putLong("latest_version_code", value).apply()

    var latestVersionName: String
        get() = prefs.getString("latest_version_name", "") ?: ""
        set(value) = prefs.edit().putString("latest_version_name", value).apply()

    var latestApkUrl: String
        get() = prefs.getString("latest_apk_url", "") ?: ""
        set(value) = prefs.edit().putString("latest_apk_url", value).apply()

    /** Build we already notified about, so the update notification fires once per release. */
    var notifiedVersionCode: Long
        get() = prefs.getLong("notified_version_code", 0L)
        set(value) = prefs.edit().putLong("notified_version_code", value).apply()

    companion object {
        private var instance: Prefs? = null

        fun getInstance(context: Context): Prefs =
            instance ?: Prefs(context.applicationContext).also { instance = it }
    }
}