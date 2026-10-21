# AudioSplit Pro

> **"Split Audio. Save Time."**  
> A high-performance, commercial-grade audio splitting web application powered by Python, FastAPI, and FFmpeg.

---

## 1. Project Overview

**AudioSplit Pro** is a modern, production-grade web application engineered to split long recordings (podcasts, lectures, interviews, meetings, audiobooks) into cleanly partitioned audio segments based on user-selected time intervals (e.g. 5, 10, 15, 20, 30 minutes, or custom durations).

### Key Highlights
- **Real FFmpeg Audio Engine**: Zero fake simulations. Analyzes containers, codecs, bitrates, sample rates, and channel layouts with `ffprobe`, and splits audio with `ffmpeg`.
- **Lossless Stream-Copy When Possible**: Avoids generation loss and re-encoding latency by utilizing FFmpeg stream-copy (`-c:a copy`) when containers match, with automatic high-quality fallback transcoding.
- **Audio Extraction from Video**: Uploading MP4 files automatically detects and isolates the audio track, outputting pure audio segments with **no black-screen video frames**.
- **Complete Trailing Audio Preservation**: The final audio segment automatically captures all remaining time so no trailing speech or music is dropped.
- **Large File Streaming**: Uploaded data streams directly to disk in 1 MB chunks, preventing memory bottlenecks even on multi-hour 500 MB+ recordings.
- **Single ZIP Archive Generation**: Download individual segment files directly or download all segments in one unified `.zip` archive.
- **Automated Lifecycle & Storage Cleanup**: Built-in 1-hour automatic retention purge and explicit client reset triggers to prevent server disk bloat.
- **Security-First Architecture**: UUID-based isolated jobs, sanitized filenames, strict regex validation, and absolute path containment to eliminate path traversal vulnerabilities.
- **Clean SaaS UI/UX**: Dark navy aesthetic with electric blue and violet accents, responsive navigation, live estimation counters, honest progress tracking, and zero framework bloat.

---

## 2. Project Folder Structure

```
AudioSplit-Pro/
│
├── backend/
│   ├── main.py                  # FastAPI server, endpoints, lifecycle, job management
│   ├── audio_processor.py       # FFmpeg/FFprobe subprocess engine, metadata & zip creation
│   └── requirements.txt         # Python dependencies
│
├── frontend/
│   ├── index.html               # Semantic HTML5 single-page application structure
│   ├── style.css                # Premium dark navy SaaS styling & responsive layout
│   └── script.js                # Vanilla JavaScript client, streaming upload, status polling
│
├── tests/
│   ├── test_audiosplit.py       # Comprehensive 47-point integration test suite
│   └── test_long_recordings.py  # 60-minute & 120-minute audio split test suite
│
├── temp_jobs/                   # Server-side isolated job directory (gitignored)
│   └── {job_id}/
│       ├── input/               # Uploaded audio stream
│       ├── output/              # Generated audio segments
│       ├── archive/             # Generated ZIP archive
│       └── metadata.json        # Persisted job state
│
├── .gitignore                   # Ignores temp files, pycache, venv, archives
├── .env.example                 # Configuration environment template
└── README.md                    # Project documentation
```

---

## 3. Technology Stack

- **Frontend**:
  - HTML5 & CSS3 (Custom design system, CSS variables, dark navy theme)
  - Vanilla JavaScript (ES6+, Fetch API, `XMLHttpRequest` upload streaming)
  - Embedded SVG iconography (Zero external CDN latency, 100% offline resilient)
- **Backend**:
  - Python 3.10+
  - FastAPI (High-performance asynchronous web framework)
  - Uvicorn (ASGI server)
  - Pydantic v2 (Data validation and type safety)
  - Python Standard Library `zipfile`, `asyncio`, `subprocess`, `pathlib`
- **Audio Processing**:
  - FFmpeg (Stream copy, sample-accurate cutting, transcode fallback)
  - FFprobe (Container analysis, duration detection, audio stream verification)

---

## 4. Prerequisites

1. **Python 3.10 or higher**
   - Check version:
     ```powershell
     python --version
     ```
2. **FFmpeg & FFprobe**
   - Both `ffmpeg` and `ffprobe` must be installed and accessible.

### Windows FFmpeg Installation

#### Option A: Install via Windows Package Manager (Winget) — Recommended
Open PowerShell and run:
```powershell
winget install --id Gyan.FFmpeg.Essentials --accept-source-agreements --accept-package-agreements
```
*Note: AudioSplit Pro includes an automated locator in `audio_processor.py` that automatically discovers Winget FFmpeg installations even before a shell restart.*

#### Option B: Manual Installation
1. Download the release build from [Gyan.dev FFmpeg](https://www.gyan.dev/ffmpeg/builds/).
2. Extract the archive to `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to your System Environment `PATH`.
4. Verify by running:
   ```powershell
   ffmpeg -version
   ffprobe -version
   ```

---

## 5. Local Setup & Startup Instructions

### Step 1: Clone or Navigate to the Project Directory
```powershell
cd d:\AudioSplit-Pro
```

### Step 2: Create and Activate Python Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```
*(On Command Prompt: `.\venv\Scripts\activate.bat`)*

### Step 3: Install Backend Dependencies
```powershell
pip install -r backend/requirements.txt
```

### Step 4: Run the Backend & Frontend Application
FastAPI is pre-configured to automatically serve both the REST API and the frontend single-page application on port 8000.

Run:
```powershell
uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

Open your browser and navigate to:
```
http://127.0.0.1:8000
```

### Step 5: (Optional) Standalone Frontend Hosting
If you prefer running the frontend separately on another local web server (e.g., Live Server on port 5500):
- Open `frontend/index.html` via your server.
- The frontend will automatically route requests to `http://localhost:8000` via pre-configured CORS headers.
- You can override the backend endpoint by setting `window.API_BASE_URL = "http://localhost:8000"` in `script.js`.

---

## 6. API Endpoint Documentation

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check endpoint; reports FFmpeg and FFprobe status |
| `POST` | `/api/audio/analyze` | Streams uploaded file to disk and extracts audio metadata via FFprobe |
| `POST` | `/api/audio/split` | Enqueues background audio splitting job with selected split duration |
| `GET` | `/api/audio/jobs/{job_id}` | Polls live processing status, current segment counter, and progress % |
| `GET` | `/api/audio/jobs/{job_id}/results` | Returns completed segment metadata and download links |
| `GET` | `/api/audio/jobs/{job_id}/download/{filename}` | Downloads a specific generated audio segment |
| `GET` | `/api/audio/jobs/{job_id}/download-zip` | Downloads all generated segments packaged as a ZIP archive |
| `DELETE`| `/api/audio/jobs/{job_id}` | Safely deletes the job directory and all associated temporary files |

### Example Payloads

#### Analyze File (`POST /api/audio/analyze`)
- **Content-Type**: `multipart/form-data`
- **Field**: `file` (Binary stream)
- **Response (200 OK)**:
```json
{
  "job_id": "b182fb89-0b44-4dd2-8952-ec7f53f938c8",
  "filename": "podcast_episode_42.mp3",
  "file_size_bytes": 52428800,
  "formatted_size": "50.00 MB",
  "duration_seconds": 7200.0,
  "formatted_duration": "02:00:00",
  "human_duration": "2 hrs 0 sec",
  "detected_format": "mp3",
  "codec": "mp3",
  "sample_rate": "44100 Hz",
  "channels": 2,
  "channel_layout": "stereo",
  "bit_rate": "320 kbps",
  "is_video_container": false,
  "available_split_options": [5, 10, 15, 20, 30]
}
```

#### Split Audio (`POST /api/audio/split`)
- **Content-Type**: `application/json`
- **Body**:
```json
{
  "job_id": "b182fb89-0b44-4dd2-8952-ec7f53f938c8",
  "split_duration_minutes": 20.0
}
```
- **Response (200 OK)**:
```json
{
  "job_id": "b182fb89-0b44-4dd2-8952-ec7f53f938c8",
  "status": "queued",
  "estimated_segments": 6,
  "message": "Splitting started. Estimated 6 segment(s)."
}
```

#### Job Results (`GET /api/audio/jobs/{job_id}/results`)
- **Response (200 OK)**:
```json
{
  "job_id": "b182fb89-0b44-4dd2-8952-ec7f53f938c8",
  "source_filename": "podcast_episode_42.mp3",
  "total_duration": 7200.0,
  "formatted_total_duration": "02:00:00",
  "split_duration_minutes": 20.0,
  "total_segments": 6,
  "segments": [
    {
      "segment_number": 1,
      "filename": "audio_part_01.mp3",
      "duration_seconds": 1200.0,
      "formatted_duration": "20:00",
      "file_size_bytes": 8738133,
      "formatted_size": "8.33 MB",
      "download_url": "/api/audio/jobs/b182fb89-0b44-4dd2-8952-ec7f53f938c8/download/audio_part_01.mp3"
    }
  ],
  "zip_filename": "podcast_episode_42_split_parts.zip",
  "zip_size_bytes": 52400000,
  "formatted_zip_size": "49.97 MB",
  "zip_download_url": "/api/audio/jobs/b182fb89-0b44-4dd2-8952-ec7f53f938c8/download-zip"
}
```

---

## 7. Automated Testing Suite

The repository includes comprehensive automated tests covering all requirements:

### Running Integration & Security Tests (47 Assertions)
```powershell
.\venv\Scripts\python tests\test_audiosplit.py
```

### Running Format Validation & Multi-Extension Tests (32 Assertions)
```powershell
.\venv\Scripts\python tests\test_format_fixes.py
```
**Tests Covered:**
- Files with multiple extensions (e.g. `Audio_Part_1.MP3.mpeg`, `Podcast.Mp3.Mpeg`)
- Uppercase extensions (`.MP3`, `.WAV`, `.M4A`, `.MP4`)
- Mixed-case extensions (`.wAv`, `.Mp3.Mpeg`)
- Unusual extensions with valid audio (`audio_custom.dat`)
- Rejection of genuinely unsupported files (`.txt`, corrupted audio files)
- End-to-end splitting and ZIP download for multi-extension audio files
**Tests Covered:**
- Server health and binary path resolution
- Valid MP3, WAV, M4A, and MP4 analysis
- MP4 video track stripping (pure audio verification)
- Rejection of invalid extensions (.txt, non-media)
- Rejection of corrupted files
- Real segment splitting and trailing audio preservation
- Duplicate request prevention
- Individual file download and ZIP archive integrity check
- Path traversal prevention (`../` and non-UUID parameters)
- Storage deletion and cleanup verification

### Running Long Recording Tests (60-minute & 120-minute)
```powershell
.\venv\Scripts\python tests\test_long_recordings.py
```
**Tests Covered:**
- 60-minute audio split into 30-minute intervals (generates 2 segments: 30:00, 30:00)
- 120-minute audio split into 20-minute intervals (generates 6 segments: 20:00 each)
- High-speed processing verification

---

## 8. Storage, Privacy & Cleanup Behavior

1. **Storage Isolation**:
   - Each uploaded file is assigned an isolated directory under `temp_jobs/{job_id}/`.
   - Temporary storage is completely private and not exposed via web directory listing.
2. **Path Traversal Shield**:
   - All endpoints enforce UUID v4 regex validation (`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`).
   - Filenames are sanitized and strictly verified via `.is_relative_to(job_output_dir)`.
3. **Automatic Expiration**:
   - A background maintenance loop runs every 10 minutes.
   - Any job older than `JOB_RETENTION_SECONDS` (default: 3600 seconds / 1 hour) that is not actively processing is automatically purged from memory and deleted from disk.
4. **Immediate Client Cleanup**:
   - Clicking "Replace File" or "Split Another Audio" sends a `DELETE /api/audio/jobs/{job_id}` request to immediately remove server files.

---

## 9. Cloud & Production Deployment Instructions

### Environment Variables
Configure via system environment or a `.env` file:
- `MAX_UPLOAD_SIZE_MB`: Configurable upload ceiling (default `500`).
- `JOB_RETENTION_SECONDS`: Job expiration timer (default `3600`).
- `HOST`: Server bind address (default `0.0.0.0` or `127.0.0.1`).
- `PORT`: Server bind port (default `8000`).

### Production Reverse Proxy (Nginx)
When deploying behind Nginx on Linux:
1. Increase `client_max_body_size` to accommodate large files:
   ```nginx
   server {
       listen 80;
       server_name audiosplit.example.com;
       return 301 https://$host$request_uri;
   }

   server {
       listen 443 ssl http2;
       server_name audiosplit.example.com;

       ssl_certificate /etc/letsencrypt/live/audiosplit.example.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/audiosplit.example.com/privkey.pem;

       client_max_body_size 600M;
       proxy_read_timeout 600s;
       proxy_send_timeout 600s;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```
2. Ensure FFmpeg is installed on Linux:
   ```bash
   sudo apt update && sudo apt install -y ffmpeg
   ```
3. Run with systemd or Gunicorn/Uvicorn workers:
   ```bash
   uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 --workers 4
   ```

---

## 10. Technical Limitations & Notes

- **Disk Ephemerality**: Server storage is local and temporary. On serverless or ephemeral container platforms (e.g. AWS Lambda without EFS), files do not persist across container reboots. A persistent volume mount is recommended for containers.
- **Audio Codec Boundaries**: MP3 and AAC stream-copying operates on compressed frame boundaries (~26ms per MP3 frame). For sample-accurate studio cutting, WAV or FLAC inputs should be utilized.
- **Authentication**: Designed initially as a single-user or public utility tool without user accounts. For multi-tenant team deployments, an authentication layer (OAuth / JWT) and rate-limiting can be attached ahead of the API.

---

## 11. License
Copyright © 2026 AudioSplit Pro. All rights reserved.
