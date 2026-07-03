package com.aira.sync

import com.google.gson.annotations.SerializedName
import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part

data class SimCdrPayload(
    @SerializedName("calls") val calls: List<CallEntry>
)

data class SimCdrResponse(
    @SerializedName("synced") val synced: Int = 0,
    @SerializedName("received") val received: Int = 0
)

data class LeadNumbersResponse(
    @SerializedName("numbers") val numbers: List<String> = emptyList(),
    @SerializedName("count") val count: Int = 0
)

data class SimRecordingResponse(
    @SerializedName("matched") val matched: Boolean = false,
    @SerializedName("call_log_id") val callLogId: String? = null
)

interface AiraApi {
    @GET("api/v1/calls/sim-lead-numbers")
    suspend fun getLeadNumbers(
        @Header("X-Sync-Token") syncToken: String
    ): Response<LeadNumbersResponse>

    @POST("api/v1/calls/sim-cdr")
    suspend fun postCalls(
        @Header("X-Sync-Token") syncToken: String,
        @Body payload: SimCdrPayload
    ): Response<SimCdrResponse>

    @Multipart
    @POST("api/v1/calls/sim-recording")
    suspend fun uploadRecording(
        @Header("X-Sync-Token") syncToken: String,
        @Part("phone_number") phoneNumber: RequestBody?,
        @Part("file_timestamp") fileTimestamp: RequestBody,
        @Part file: MultipartBody.Part
    ): Response<SimRecordingResponse>
}
