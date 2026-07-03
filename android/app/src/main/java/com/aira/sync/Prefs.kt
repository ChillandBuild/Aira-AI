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

    var recordingFolderPath: String
        get() = prefs.getString("recording_folder_path", "") ?: ""
        set(value) = prefs.edit().putString("recording_folder_path", value).apply()

    var lastScannedRecordingMs: Long
        get() = prefs.getLong("last_scanned_recording_ms", 0L)
        set(value) = prefs.edit().putLong("last_scanned_recording_ms", value).apply()

    companion object {
        private var instance: Prefs? = null

        fun getInstance(context: Context): Prefs =
            instance ?: Prefs(context.applicationContext).also { instance = it }
    }
}