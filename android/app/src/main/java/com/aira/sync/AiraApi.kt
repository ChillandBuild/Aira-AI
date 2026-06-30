package com.aira.sync

import com.google.gson.annotations.SerializedName
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST

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
}