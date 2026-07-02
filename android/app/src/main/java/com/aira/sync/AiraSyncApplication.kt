package com.aira.sync

import android.Manifest
import android.app.Application
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import androidx.work.*
import java.util.concurrent.TimeUnit

class AiraSyncApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        schedulePeriodicSync()
        // Only (re)start the foreground service if the user already granted
        // READ_CALL_LOG in a prior session — e.g. relaunching the app after
        // it was killed. First-run setup happens via MainActivity once
        // permissions are granted, not here.
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CALL_LOG) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            SyncService.start(this)
        }
    }

    private fun schedulePeriodicSync() {
        val workRequest = PeriodicWorkRequestBuilder<SyncWorker>(30, TimeUnit.MINUTES)
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build()
            )
            .build()
        WorkManager.getInstance(this)
            .enqueueUniquePeriodicWork(
                "sim_cdr_sync",
                ExistingPeriodicWorkPolicy.KEEP,
                workRequest
            )
    }
}