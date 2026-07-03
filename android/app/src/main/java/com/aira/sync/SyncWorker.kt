package com.aira.sync

import android.app.Application
import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

class SyncWorker(appContext: Context, workerParams: WorkerParameters) :
    CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        try {
            val prefs = Prefs.getInstance(applicationContext)
            val sinceMs = if (prefs.lastSyncedTimestampMs == 0L) {
                System.currentTimeMillis() - TimeUnit.DAYS.toMillis(7)
            } else {
                prefs.lastSyncedTimestampMs
            }

            val calls = CallLogReader.readCallsSince(applicationContext, sinceMs)
            if (calls.isEmpty()) {
                return@withContext Result.success()
            }

            val retrofit = Retrofit.Builder()
                .baseUrl(prefs.serverUrl)
                .addConverterFactory(GsonConverterFactory.create())
                .build()

            val api = retrofit.create(AiraApi::class.java)

            // Fetch the caller's assigned-lead numbers for on-device filtering.
            // Fail closed: if we can't get the lead set, do NOT upload anything —
            // never risk sending a personal call to the server.
            val leadResp = api.getLeadNumbers(prefs.syncToken)
            if (!leadResp.isSuccessful) {
                Log.e("SyncWorker", "Lead-number fetch failed: HTTP ${leadResp.code()}")
                return@withContext Result.retry()
            }
            val leadSet = leadResp.body()?.numbers?.toHashSet() ?: hashSetOf()

            // Keep only calls to/from a known lead; personal calls never leave the phone.
            val workCalls = calls.filter { normalizePhone(it.number) in leadSet }
            val newBoundary = calls.maxOfOrNull { it.date } ?: sinceMs

            if (workCalls.isEmpty()) {
                // Nothing lead-related in this batch — advance past the personal
                // calls so we don't rescan them, and finish cleanly.
                prefs.lastSyncedTimestampMs = newBoundary
                Log.d("SyncWorker", "No lead calls in ${calls.size} entries; boundary: $newBoundary")
                return@withContext Result.success()
            }

            val response = api.postCalls(prefs.syncToken, SimCdrPayload(workCalls))
            if (!response.isSuccessful) {
                Log.e("SyncWorker", "Call log sync failed: HTTP ${response.code()}")
                return@withContext Result.retry()
            }
            prefs.lastSyncedTimestampMs = newBoundary
            Log.d("SyncWorker", "Synced ${workCalls.size}/${calls.size} lead calls, boundary: $newBoundary")

            // Recording scan — best effort, does not affect call-log sync outcome.
            val recordingFolder = prefs.recordingFolderPath
            if (!recordingFolder.isNullOrBlank()) {
                val sinceRecording = prefs.lastScannedRecordingMs
                val leadCallWindows = workCalls.map { it.date to normalizePhone(it.number) }
                val recordings = RecordingScanner.scanNewRecordings(recordingFolder, sinceRecording, leadSet, leadCallWindows)
                if (recordings.isNotEmpty()) {
                    Log.i("SyncWorker", "Found ${recordings.size} new recordings to scan")
                    var maxModified = sinceRecording
                    for (recording in recordings) {
                        try {
                            val phoneNumber = recording.phoneNumber ?: ""
                            val timestamp = recording.lastModified
                            val requestFile = recording.file.asRequestBody("audio/*".toMediaType())
                            val body = MultipartBody.Part.createFormData("file", recording.file.name, requestFile)
                            val phoneBody = phoneNumber.toRequestBody("text/plain".toMediaType())
                            val timeBody = timestamp.toString().toRequestBody("text/plain".toMediaType())
                            val uploadResp = api.uploadRecording(prefs.syncToken, phoneBody, timeBody, body)
                            if (uploadResp.isSuccessful) {
                                Log.d("SyncWorker", "Uploaded recording ${recording.file.name}")
                            } else {
                                Log.w("SyncWorker", "Recording upload failed: HTTP ${uploadResp.code()}")
                            }
                            if (recording.lastModified > maxModified) {
                                maxModified = recording.lastModified
                            }
                        } catch (e: Exception) {
                            Log.w("SyncWorker", "Recording upload failed for ${recording.file.name}", e)
                        }
                    }
                    prefs.lastScannedRecordingMs = maxModified
                }
            }

            return@withContext Result.success()
        } catch (e: Exception) {
            Log.e("SyncWorker", "Sync error", e)
            return@withContext Result.retry()
        }
    }

    companion object {
        fun enqueueNow(context: Context) {
            val request = androidx.work.OneTimeWorkRequestBuilder<SyncWorker>()
                .setConstraints(
                    androidx.work.Constraints.Builder()
                        .setRequiredNetworkType(androidx.work.NetworkType.CONNECTED)
                        .build()
                )
                .build()
            androidx.work.WorkManager.getInstance(context).enqueue(request)
        }
    }
}