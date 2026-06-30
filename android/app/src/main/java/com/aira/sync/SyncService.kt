package com.aira.sync

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.provider.CallLog
import androidx.core.app.NotificationCompat

class SyncService : Service() {
    private val channelId = "aira_sync_channel"
    private val notificationId = 1
    private var observer: android.database.ContentObserver? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(notificationId, createNotification())
        registerCallLogObserver()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return START_STICKY
    }

    override fun onDestroy() {
        observer?.let { contentResolver.unregisterContentObserver(it) }
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "Aira Sync",
                NotificationManager.IMPORTANCE_LOW
            )
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(channel)
        }
    }

    private fun createNotification(): Notification {
        return NotificationCompat.Builder(this, channelId)
            .setContentTitle("Aira Sync")
            .setContentText("Active")
            .setSmallIcon(R.drawable.ic_notification)
            .build()
    }

    private fun registerCallLogObserver() {
        observer = object : android.database.ContentObserver(null) {
            override fun onChange(selfChange: Boolean) {
                SyncWorker.enqueueNow(applicationContext)
            }
        }
        contentResolver.registerContentObserver(
            CallLog.Calls.CONTENT_URI,
            true,
            observer!!
        )
    }

    companion object {
        fun start(context: Context) {
            val intent = Intent(context, SyncService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
    }
}