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
import java.io.File

class MainActivity : AppCompatActivity() {
    companion object {
        const val REQUEST_FOLDER_PICK = 1001
    }

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
        val recordingPathText = findViewById<TextView>(R.id.recordingPathText)
        val recordingStatus = findViewById<TextView>(R.id.recordingStatus)
        val changeRecordingFolderBtn = findViewById<Button>(R.id.changeRecordingFolderBtn)

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

        changeRecordingFolderBtn.setOnClickListener {
            openFolderPicker()
        }

        updatePermissionStatus()
        updateLastSynced()
        updateRecordingFolderUi(recordingPathText, recordingStatus)
    }

    override fun onResume() {
        super.onResume()
        // Re-run the permission chain in case the user just came back from a permission
        // Settings screen (e.g. All Files Access) without us getting a callback for it.
        // Only resume once they've actually started connecting (guarded by syncToken),
        // otherwise this would pop permission prompts on every app foreground.
        if (::prefs.isInitialized && prefs.syncToken.isNotBlank()) {
            checkAndRequestPermissions()
        }
    }

    private fun updateRecordingFolderUi(pathText: TextView, statusText: TextView) {
        val path = prefs.recordingFolderPath
        pathText.text = if (path.isBlank()) "No folder selected" else path
        val exists = path.isNotBlank() && File(path).exists() && File(path).isDirectory
        statusText.text = if (exists) "✓" else ""
        statusText.setTextColor(ContextCompat.getColor(this, android.R.color.holo_green_dark))
    }

    private fun openFolderPicker() {
        val intent = android.content.Intent(this, FolderPickerActivity::class.java)
        startActivityForResult(intent, REQUEST_FOLDER_PICK)
    }

    @Deprecated("")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: android.content.Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_FOLDER_PICK && resultCode == RESULT_OK && data != null) {
            val path = data.getStringExtra("folder_path")
            if (!path.isNullOrBlank()) {
                prefs.recordingFolderPath = path
                val pathText = findViewById<TextView>(R.id.recordingPathText)
                val statusText = findViewById<TextView>(R.id.recordingStatus)
                updateRecordingFolderUi(pathText, statusText)
            }
        }
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
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.R &&
                    !android.os.Environment.isExternalStorageManager() -> {
                requestAllFilesAccess()
            }
            else -> detectRecordingFolderAndSchedule()
        }
    }

    private fun requestAllFilesAccess() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            try {
                val intent = android.content.Intent(android.provider.Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
                intent.data = android.net.Uri.parse("package:$packageName")
                startActivity(intent)
            } catch (e: Exception) {
                val intent = android.content.Intent(android.provider.Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)
                startActivity(intent)
            }
        }
    }

    private fun detectRecordingFolderAndSchedule() {
        val detected = RecordingScanner.detectDefaultFolder()
        if (detected != null && prefs.recordingFolderPath.isBlank()) {
            prefs.recordingFolderPath = detected
        }
        scheduleWork()
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
        permissionStatus.text = if (hasCallLog) "Permission: Granted" else "Permission: Required"
    }

    private fun updateLastSynced() {
        val lastSync = prefs.lastSyncedTimestampMs
        lastSyncedText.text = if (lastSync > 0) {
            "Last synced: ${java.util.Date(lastSync)}"
        } else {
            "Last synced: Never"
        }
    }
}