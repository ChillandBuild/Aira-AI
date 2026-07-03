package com.aira.sync

import android.util.Log
import java.io.File
import java.util.regex.Pattern

object RecordingScanner {
    private val TAG = "RecordingScanner"
    private val AUDIO_EXTENSIONS = setOf("mp3", "m4a", "wav", "amr", "3gp")
    private val PHONE_PATTERN = Pattern.compile("(\\d{10,})")
    // Recorder apps can flush the file to disk a little after the call-log entry's
    // timestamp is written, so allow slack when correlating by time instead of filename.
    private const val LEAD_CALL_WINDOW_MS = 5 * 60 * 1000L

    fun detectDefaultFolder(): String? {
        val candidates = listOf(
            "/storage/emulated/0/MIUI/sound_recorder/call_rec",
            "/storage/emulated/0/Call",
            "/storage/emulated/0/Recordings/Call Recordings",
            "/storage/emulated/0/Music/Recordings/Call Recordings",
            "/storage/emulated/0/Recordings/Call Recordings",
            "/storage/emulated/0/Record/Call",
            "/storage/emulated/0/CallRecordings"
        )
        for (path in candidates) {
            val file = File(path)
            if (file.exists() && file.isDirectory) {
                return path
            }
        }
        return null
    }

    fun scanNewRecordings(
        folderPath: String,
        sinceMs: Long,
        leadNumbers: Set<String>,
        leadCallWindows: List<Pair<Long, String>>
    ): List<RecordingFile> {
        val folder = File(folderPath)
        if (!folder.exists() || !folder.isDirectory) {
            Log.w(TAG, "Recording folder not found: $folderPath")
            return emptyList()
        }

        val files = folder.listFiles() ?: return emptyList()
        val results = mutableListOf<RecordingFile>()

        for (file in files) {
            if (!file.isFile) continue
            val ext = file.extension.lowercase()
            if (ext !in AUDIO_EXTENSIONS) continue

            val lastModified = file.lastModified()
            if (lastModified <= sinceMs) continue

            val extractedNumber = extractPhoneNumber(file.name)
            val passesLeadFilter = if (extractedNumber != null) {
                extractedNumber in leadNumbers
            } else {
                leadCallWindows.any { (callTimestamp, _) ->
                    Math.abs(lastModified - callTimestamp) <= LEAD_CALL_WINDOW_MS
                }
            }

            if (passesLeadFilter) {
                results.add(
                    RecordingFile(
                        file = file,
                        phoneNumber = extractedNumber,
                        lastModified = lastModified
                    )
                )
            }
        }

        return results.sortedBy { it.lastModified }
    }

    private fun extractPhoneNumber(fileName: String): String? {
        val baseName = fileName.substringBeforeLast('.')
        val matcher = PHONE_PATTERN.matcher(baseName)
        if (matcher.find()) {
            val candidate = matcher.group(1) ?: return null
            val normalized = normalizePhone(candidate)
            if (normalized.length == 12 && normalized.startsWith("+91")) {
                return normalized
            }
        }
        return null
    }

    fun normalizePhone(raw: String?): String {
        var digits = (raw ?: "").filter { it.isDigit() }
        if (digits.length == 12 && digits.startsWith("91")) {
            digits = digits.substring(2)
        }
        return if (digits.length == 10) "+91$digits" else digits
    }
}

data class RecordingFile(
    val file: java.io.File,
    val phoneNumber: String?,
    val lastModified: Long
)