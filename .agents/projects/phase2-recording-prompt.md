# Task: Aira Sync Phase 2 — Call Recording Upload

You're extending an existing Android app ("Aira Sync") and FastAPI backend. Phase 1 (call-log metadata sync, no recordings) is already built and live in production. This is Phase 2: sync the actual recorded audio files so they feed the existing AI transcription/evaluation pipeline.

## Stack

- Backend: FastAPI (`backend/app/routes/calls.py`), Supabase Postgres + Storage, Groq (Whisper transcription + Llama evaluation)
- Android: Kotlin, minSdk 26 / targetSdk 34, Retrofit + OkHttp + Gson, WorkManager, no Jetpack Compose (plain XML layouts + `AppCompatActivity`)
- Package: `com.aira.sync`

## Hard Invariants (never break these)

1. **Call Recordings: Uploaded to Supabase Storage only, never saved to local disk.** The backend must NOT write the audio to Render's local filesystem at any point — hold bytes in memory and stream straight to `db.storage.from_("call-recordings").upload(...)`, exactly like the existing TeleCMI recording path does.
2. **Multi-Tenancy & Security**: every DB write/read must be scoped by `tenant_id`. This endpoint has no user session — auth is via the per-caller `X-Sync-Token` header (see below), and `tenant_id` comes from resolving that token, never from client input.
3. Never write to `call_logs.notes`, `tags`, `quality_rating`, `manual_started_at`, `manual_ended_at` from this pipeline — those are human-owned fields from the wrap-up form. This endpoint may only touch `recording_url` (and downstream, `transcript`/`ai_summary`/`evaluation` via the existing summarization call).
4. On-device privacy filter is mandatory and fail-closed: a recording file must only ever be uploaded if it matches (by phone number correlation, or lead+time-window as fallback) a lead the caller is assigned to. If the lead-number fetch fails, do nothing — never upload speculatively.

## What already exists (Phase 1 — do not reimplement, reuse/extend)

**`backend/app/routes/calls.py`** — SIM sync section (search `# The Aira Sync APK reads the phone's native call log`):
- `_resolve_sim_caller(request) -> dict` — authenticates via `X-Sync-Token` header, returns `{id, tenant_id, active}`. Raises 401 if missing/invalid/inactive. **Reuse this exact function for the new endpoint's auth.**
- `_normalize_sim_phone(phone: str) -> str` — normalizes any raw number format to `+91XXXXXXXXXX` (the format `leads.phone` is stored in). Reuse for any filename-based number matching.
- `POST /sim-cdr` (`sim_cdr` handler) + `_ingest_sim_call()` — ingests call-log entries, creates/enriches `call_logs` rows, dedups on `(caller_id, call_sid, provider='sim_basic')` via a partial unique index (migration 122).
- `GET /sim-lead-numbers` (`sim_lead_numbers` handler) — returns the caller's assigned-lead phone numbers, normalized, for on-device filtering. Already used by the call-log sync; reuse the same fetched set for recording filtering (don't add a second endpoint for this).
- `_SIM_ENRICH_WINDOW_HOURS = 12` — the time window already used to match a fresh sync event to an existing `call_logs` row by caller+lead+time. Use the same window/pattern to match a recording file to a `call_logs` row.
- `async def _process_telecmi_recording(call_log_id, recording_url)` and `async def _run_summarization(call_log_id, recording_url, force=False)` — the existing recording→transcription→evaluation pipeline (Groq Whisper transcribe, gated by outcome/duration, then `analyze_call`). **Reuse `_run_summarization` unchanged** once you've set `recording_url` on a row — do not duplicate transcription/evaluation logic.
- Storage bucket is `"call-recordings"`, path pattern `f"{call_log_id}.mp3"`, uploaded via `db.storage.from_("call-recordings").upload(path, bytes, {"content-type": "audio/mpeg", "upsert": "true"})`, then `get_public_url(...)`.

**Android (`android/app/src/main/java/com/aira/sync/`)**:
- `AiraApi.kt` — Retrofit interface, `X-Sync-Token` header auth pattern, Gson `@SerializedName` DTOs. Add new endpoints here in the same style.
- `Prefs.kt` — `SharedPreferences` wrapper (`serverUrl`, `syncToken`, `lastSyncedTimestampMs`). Add new persisted fields here (recording folder URI/path, last-scanned-recording timestamp) the same way.
- `SyncWorker.kt` — `CoroutineWorker`, fetches lead numbers first (fail-closed if that fetch fails), filters, then syncs. Add recording-folder scanning as an additional step in the same worker (or a sibling worker enqueued alongside it) — same fail-closed-on-lead-fetch-failure pattern.
- `CallLogReader.kt` — has `normalizePhone()` mirroring the Python `_normalize_sim_phone` exactly. Reuse/extend, don't reimplement.
- `MainActivity.kt` / `activity_main.xml` — simple `EditText` + `Button` settings screen, `ActivityResultContracts.RequestPermission()` for runtime permissions. Extend with the recording-folder UI (see below), following the same plain-XML style — no new UI framework.
- `AndroidManifest.xml` — currently has `READ_CALL_LOG`, `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_DATA_SYNC`, `POST_NOTIFICATIONS`, `INTERNET`, `RECEIVE_BOOT_COMPLETED`.
- Gradle deps already present: `retrofit:2.11.0`, `converter-gson:2.11.0`, `okhttp:4.12.0`, `work-runtime-ktx:2.9.1`, `core-ktx:1.13.1`, `appcompat:1.7.0`. compileSdk/targetSdk 34.
- Latest migration file is `127_admin_subscription_plans.sql` — your new migration must be `128_<name>.sql`.

## What to build

### 1. Android: recording folder access (All Files Access, not SAF)

Use `MANAGE_EXTERNAL_STORAGE` (All Files Access), not the Storage Access Framework picker. Reasoning already settled: this app is sideloaded (not Play Store distributed), and All Files Access lets us both auto-detect known OEM paths and show/browse raw filesystem paths, which SAF's opaque `content://` tree URIs can't do.

- Add `<uses-permission android:name="android.permission.MANAGE_EXTERNAL_STORAGE" tools:ignore="ScopedStorage" />` to the manifest (needs `xmlns:tools`).
- On first run / in Settings, auto-detect the recording folder by checking a known-path list for existence (`File(path).exists() && File(path).isDirectory()`), in this order:
  - MIUI/Xiaomi: `/storage/emulated/0/MIUI/sound_recorder/call_rec`
  - Samsung: `/storage/emulated/0/Call`
  - OnePlus (OxygenOS): `/storage/emulated/0/Recordings/Call Recordings`, and `/storage/emulated/0/Music/Recordings/Call Recordings` (newer OxygenOS)
  - Oppo/Realme (ColorOS): `/storage/emulated/0/Recordings/Call Recordings` (dedupe against OnePlus if same path)
  - Vivo (FunTouch/OriginOS): `/storage/emulated/0/Record/Call`
  - Stock Android / generic: `/storage/emulated/0/CallRecordings`
- Settings UI (extend `activity_main.xml` + `MainActivity.kt`): a card showing the detected path with a status indicator (detected vs. not-found), and a **"Change Source Folder"** button that opens a minimal in-app folder browser (simple `ListView`/`RecyclerView` over `File.listFiles()`, starting at `/storage/emulated/0/`) letting the user navigate and select any folder manually — mirrors this reference UX (screenshot from a comparable CRM app, DealConverter): auto-detected path shown with a green checkmark, path displayed as plain text, single "Change Source Folder" CTA below it, plus a short explainer line. Match that shape — detected-path card, checkmark, single change button, short help text — using this app's existing plain-XML/Material style, not a redesign.
- Persist the chosen absolute path in `Prefs.kt` (new field, e.g. `recordingFolderPath`).
- Request `MANAGE_EXTERNAL_STORAGE` via `Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION` intent (this permission can't be requested via the normal runtime-permission dialog) — add to the same `checkAndRequestPermissions()` flow in `MainActivity.kt`, after the existing `READ_CALL_LOG`/`POST_NOTIFICATIONS` checks. Show a plain-language rationale before sending the user to Settings (same tone as the existing permission flow).

### 2. Android: scan + upload

- New Kotlin object/class (e.g. `RecordingScanner.kt`) that, given the configured folder path and a "since" timestamp (new `Prefs` field `lastScannedRecordingMs`), lists files in that folder with `lastModified() > since`, filtered to audio extensions (`.mp3`, `.m4a`, `.wav`, `.amr`, `.3gp` — OEMs vary).
- For each new file: attempt to extract a phone number from the filename via regex (handle common OEM patterns like `<number>_<date>_<time>.ext`, `<name>_<number>.ext`; if no plausible 10+ digit run is found, treat as unmatched-by-number and fall back to timestamp-only matching server-side).
- Filter against the **same lead-number set already fetched in `SyncWorker`** for the call-log sync (do not add a second `/sim-lead-numbers` call) — only files whose extracted number is in that set (or, for unmatched-by-number files, defer the decision to the server, which will gate by caller+time window anyway) get uploaded.
- Upload via a new Retrofit multipart endpoint (add to `AiraApi.kt`):
  ```kotlin
  @Multipart
  @POST("api/v1/calls/sim-recording")
  suspend fun uploadRecording(
      @Header("X-Sync-Token") syncToken: String,
      @Part("phone_number") phoneNumber: RequestBody?,   // nullable — omitted if not extracted
      @Part("file_timestamp") fileTimestamp: RequestBody, // epoch ms, file's lastModified()
      @Part file: MultipartBody.Part
  ): Response<SimRecordingResponse>
  ```
- On success, advance `lastScannedRecordingMs` to the max `lastModified()` seen in this batch (same boundary-advance pattern `SyncWorker` already uses for call-log sync — advance past the batch even if some individual files fail to match, so failures don't get rescanned forever; log failures, don't retry indefinitely).
- Wire this scan into the existing `SyncWorker.doWork()` (after the existing call-log sync block) or a second `CoroutineWorker` enqueued alongside it on the same `WorkManager` periodic schedule — your choice, but it must ride the existing sync cadence, not introduce a separate schedule.
- No WiFi constraint — upload on any connection (already decided).

### 3. Backend: `POST /sim-recording` endpoint

Add to `backend/app/routes/calls.py`, near the existing sim-cdr section:

```python
@public_router.post("/sim-recording")
async def sim_recording(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    phone_number: str | None = Form(default=None),
    file_timestamp: int = Form(...),  # epoch ms
):
    """Ingest a call-recording file from the Aira Sync APK and match it to
    the corresponding call_logs row (created by /sim-cdr or the PWA wrap-up).
    """
    caller = _resolve_sim_caller(request)
    caller_id = caller["id"]
    tenant_id = caller["tenant_id"]
    db = get_supabase()

    # 1. Resolve the target call_logs row.
    #    - If phone_number given: normalize it, find the lead, then find the
    #      matching call_logs row by caller+lead+time window (reuse the same
    #      _SIM_ENRICH_WINDOW_HOURS pattern _ingest_sim_call already uses,
    #      but match on call_dt closeness to file_timestamp within the window,
    #      picking the closest row rather than just "most recent").
    #    - If phone_number is absent: match by caller_id + file_timestamp
    #      falling within [call started, call started + generous buffer] across
    #      this caller's recent sim_basic rows — still gated to only rows tied
    #      to an actual lead (never create new rows here, never touch a row
    #      with no lead_id).
    #    - No match found → 404 (log and drop; do not create a call_logs row
    #      from a recording alone).

    # 2. Read file bytes into memory (per Hard Invariant #5, never touch local
    #    disk), upload to the "call-recordings" bucket at f"{call_log_id}.mp3"
    #    (reuse the exact upload call from _process_telecmi_recording),
    #    get_public_url, update call_logs.recording_url ONLY (no other fields).

    # 3. background_tasks.add_task(_run_summarization, call_log_id, public_url)
    #    — reuse unchanged.

    return {"matched": True, "call_log_id": call_log_id}
```

Fill in the actual matching query logic following the exact Supabase query style already used in `_ingest_sim_call` (`.eq()`/`.gte()`/`.lte()`/`.order()`/`.limit(1)`/`.maybe_single()`), same `tenant_id`/`caller_id` scoping. Add `File`, `Form`, `UploadFile` to the existing `fastapi` import line at the top of the file if not already imported.

### 4. Tests

Follow the exact static-test style already in `backend/tests/test_sim_cdr_static.py` (source-text assertions against `app/routes/calls.py`, since the sandbox this was originally built in lacks the full `httpx`/`fastapi` dependency stack for live imports — but write real pytest tests assuming a normal dev environment will run them too). At minimum:
- `test_sim_recording_endpoint_exists` — asserts the route, `_resolve_sim_caller` reuse, and multipart params are present.
- `test_sim_recording_never_creates_call_logs_row` — asserts there's no `.insert(` call in the sim-recording matching path (it must only update an existing row, never create one from a recording alone).
- `test_sim_recording_only_updates_recording_url` — same anchoring technique as `test_sim_cdr_never_writes_human_owned_fields` (anchor on unique content, not generic prefixes — this file has multiple `.update(` calls) — assert the update payload for this endpoint contains only `recording_url`.
- `test_sim_recording_reuses_run_summarization` — asserts `_run_summarization` is called, not a duplicate transcription implementation.

### 5. Migration

`backend/supabase/migrations/128_<descriptive_name>.sql` — only if you introduce new columns (e.g. if you decide to store `sim_recording_matched_at` or similar bookkeeping on `call_logs` — not required, but if you add any column, migration must follow the same style as `122_sim_sync_token.sql`: `alter table ... add column if not exists ...`, plus any index `if not exists`).

## Do NOT

- Do not touch `notes`, `tags`, `quality_rating`, `manual_started_at`, `manual_ended_at` from this pipeline.
- Do not write audio bytes to local disk anywhere in the backend.
- Do not add a second `/sim-lead-numbers`-equivalent endpoint — reuse the existing one.
- Do not reimplement transcription/evaluation — call `_run_summarization`.
- Do not create new `call_logs` or `leads` rows from the recording-upload path — it only enriches an existing row.
- Do not gate recording upload on WiFi.
- Do not use the Storage Access Framework (`ACTION_OPEN_DOCUMENT_TREE`) — use `MANAGE_EXTERNAL_STORAGE`.

## Deliverable

Working code only. No trailing summaries, no explanations outside code comments — this will be reviewed and tested separately.
