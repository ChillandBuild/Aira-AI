package com.aira.sync

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

class MainActivity : AppCompatActivity() {
    private lateinit var prefs: Prefs
    private lateinit var serverUrlInput: EditText
    private lateinit var syncTokenInput: EditText
    private lateinit var saveConnectBtn: Button
    private lateinit var syncNowBtn: Button
    private lateinit var permissionStatus: TextView
    private lateinit var lastSyncedText: TextView

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        updatePermissionStatus()
        if (granted) {
            scheduleWork()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        prefs = Prefs.getInstance(this)

        serverUrlInput = findViewById(R.id.serverUrlInput)
        syncTokenInput = findViewById(R.id.syncTokenInput)
        saveConnectBtn = findViewById(R.id.saveConnectBtn)
        syncNowBtn = findViewById(R.id.syncNowBtn)
        permissionStatus = findViewById(R.id.permissionStatus)
        lastSyncedText = findViewById(R.id.lastSyncedText)

        serverUrlInput.setText(prefs.serverUrl)
        syncTokenInput.setText(prefs.syncToken)

        saveConnectBtn.setOnClickListener {
            prefs.serverUrl = serverUrlInput.text.toString()
            prefs.syncToken = syncTokenInput.text.toString()
            checkAndRequestPermissions()
        }

        syncNowBtn.setOnClickListener {
            SyncWorker.enqueueNow(this)
            Toast.makeText(this, "Sync started", Toast.LENGTH_SHORT).show()
        }

        updatePermissionStatus()
        updateLastSynced()
    }

    private fun checkAndRequestPermissions() {
        when {
            ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.READ_CALL_LOG
            ) != PackageManager.PERMISSION_GRANTED -> {
                requestPermissionLauncher.launch(Manifest.permission.READ_CALL_LOG)
            }
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                    ContextCompat.checkSelfPermission(
                        this,
                        Manifest.permission.POST_NOTIFICATIONS
                    ) != PackageManager.PERMISSION_GRANTED -> {
                requestPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
            else -> scheduleWork()
        }
    }

    private fun scheduleWork() {
        SyncService.start(this)
        SyncWorker.enqueueNow(this)
        Toast.makeText(this, "Connected", Toast.LENGTH_SHORT).show()
    }

    private fun updatePermissionStatus() {
        val hasCallLog = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.READ_CALL_LOG
        ) == PackageManager.PERMISSION_GRANTED
        if (hasCallLog) {
            permissionStatus.text = getString(R.string.permission_granted)
            permissionStatus.setBackgroundResource(R.drawable.bg_pill_success)
            permissionStatus.setTextColor(ContextCompat.getColor(this, R.color.aira_success))
        } else {
            permissionStatus.text = getString(R.string.permission_required)
            permissionStatus.setBackgroundResource(R.drawable.bg_pill_danger)
            permissionStatus.setTextColor(ContextCompat.getColor(this, R.color.aira_danger))
        }
    }

    private fun updateLastSynced() {
        val lastSync = prefs.lastSyncedTimestampMs
        lastSyncedText.text = if (lastSync > 0) {
            java.text.DateFormat.getDateTimeInstance(
                java.text.DateFormat.MEDIUM,
                java.text.DateFormat.SHORT
            ).format(java.util.Date(lastSync))
        } else {
            "Never"
        }
    }
}