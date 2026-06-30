package com.aira.sync

import android.content.ContentResolver
import android.content.Context
import android.database.Cursor
import android.provider.CallLog
import com.google.gson.annotations.SerializedName

data class CallEntry(
    @SerializedName("phone_number") val number: String,
    @SerializedName("call_type") val type: Int,
    @SerializedName("timestamp") val date: Long,
    @SerializedName("duration") val duration: Long,
    @SerializedName("entry_id") val entryId: String
)

/**
 * Normalize a phone number to bare digits, dropping a leading India 91 country
 * code. MUST mirror the backend's _normalize_sim_phone so the device can match
 * call-log numbers against the lead set the server returns.
 */
fun normalizePhone(raw: String?): String {
    var digits = (raw ?: "").filter { it.isDigit() }
    if (digits.length == 12 && digits.startsWith("91")) {
        digits = digits.substring(2)
    }
    return digits
}

object CallLogReader {
    fun readCallsSince(context: Context, sinceMs: Long): List<CallEntry> {
        val resolver: ContentResolver = context.contentResolver
        val projection = arrayOf(
            CallLog.Calls.NUMBER,
            CallLog.Calls.TYPE,
            CallLog.Calls.DATE,
            CallLog.Calls.DURATION,
            CallLog.Calls._ID
        )
        val selection = "${CallLog.Calls.DATE} > ?"
        val selectionArgs = arrayOf(sinceMs.toString())
        val sortOrder = "${CallLog.Calls.DATE} ASC"

        val calls = mutableListOf<CallEntry>()
        val cursor: Cursor? = resolver.query(
            CallLog.Calls.CONTENT_URI,
            projection,
            selection,
            selectionArgs,
            sortOrder
        )

        cursor?.use {
            while (it.moveToNext()) {
                val number = it.getString(it.getColumnIndexOrThrow(CallLog.Calls.NUMBER)) ?: ""
                val type = it.getInt(it.getColumnIndexOrThrow(CallLog.Calls.TYPE))
                val date = it.getLong(it.getColumnIndexOrThrow(CallLog.Calls.DATE))
                val duration = it.getLong(it.getColumnIndexOrThrow(CallLog.Calls.DURATION))
                val entryId = it.getString(it.getColumnIndexOrThrow(CallLog.Calls._ID)) ?: continue
                calls.add(CallEntry(number, type, date, duration, entryId))
            }
        }

        return calls
    }
}