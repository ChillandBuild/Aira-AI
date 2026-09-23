package com.aira.sync

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.pm.PackageInfoCompat
import com.google.gson.JsonParser
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

/**
 * Aira Sync is sideloaded (no Play Store), so it cannot auto-update. Each sync run
 * reads version.json — published next to the APK — and, when a newer build exists,
 * raises one notification per release. Android still needs the user to tap Install.
 */
object UpdateChecker {
    private const val VERSION_URL =
        "https://ayftynkgmfkaqmmnlmoc.supabase.co/storage/v1/object/public/app-releases/version.json"
    private const val CHANNEL_ID = "aira_sync_update"
    private const val NOTIFICATION_ID = 2001
    private const val TAG = "UpdateChecker"

    private val http = OkHttpClient.Builder()
        .callTimeout(10, TimeUnit.SECONDS)
        .build()

    fun currentVersionCode(context: Context): Long {
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        return PackageInfoCompat.getLongVersionCode(info)
    }

    fun isUpdateAvailable(context: Context, prefs: Prefs): Boolean =
        prefs.latestVersionCode > currentVersionCode(context) && prefs.latestApkUrl.isNotBlank()

    /** Never throws: a failed check must not break syncing. */
    fun checkAndNotify(context: Context) {
        try {
            val prefs = Prefs.getInstance(context)
            val body = http.newCall(Request.Builder().url(VERSION_URL).build())
                .execute().use { if (it.isSuccessful) it.body?.string() else null }
                ?: return
            val json = JsonParser.parseString(body).asJsonObject
            prefs.latestVersionCode = json.get("versionCode").asLong
            prefs.latestVersionName = json.get("versionName")?.asString ?: ""
            prefs.latestApkUrl = json.get("apkUrl").asString

            if (isUpdateAvailable(context, prefs) && prefs.notifiedVersionCode < prefs.latestVersionCode) {
                if (notify(context, prefs)) prefs.notifiedVersionCode = prefs.latestVersionCode
            }
        } catch (e: Exception) {
            Log.w(TAG, "Update check failed", e)
        }
    }

    /** Returns true only if the notification was actually posted (permission granted). */
    private fun notify(context: Context, prefs: Prefs): Boolean {
        val manager = NotificationManagerCompat.from(context)
        if (!manager.areNotificationsEnabled()) return false
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.getSystemService(NotificationManager::class.java).createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "Aira Sync updates", NotificationManager.IMPORTANCE_DEFAULT)
            )
        }
        val open = PendingIntent.getActivity(
            context, 0, downloadIntent(prefs.latestApkUrl),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val label = prefs.latestVersionName.ifBlank { "a new version" }
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("Aira Sync update available")
            .setContentText("Tap to download $label and install it.")
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        return try {
            manager.notify(NOTIFICATION_ID, notification)
            true
        } catch (e: SecurityException) {
            false
        }
    }

    fun downloadIntent(url: String): Intent =
        Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
}
