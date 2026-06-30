package com.aira.sync

import android.app.Application
import androidx.work.*
import java.util.concurrent.TimeUnit

class AiraSyncApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        schedulePeriodicSync()
        SyncService.start(this)
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