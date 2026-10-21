"""
AudioSplit Pro - FastAPI Backend
High-Performance Audio Splitting API
"""

import os
import re
import sys
import uuid
import time
import json
import math
import shutil
import asyncio
import logging
import concurrent.futures
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Ensure backend directory is in path
CURRENT_DIR = Path(__file__).resolve().parent
BASE_DIR = CURRENT_DIR.parent
sys.path.insert(0, str(CURRENT_DIR))

from audio_processor import (
    FFMPEG_BIN,
    FFPROBE_BIN,
    inspect_audio_file,
    determine_output_profile,
    execute_split_segment,
    verify_audio_file,
    create_zip_archive,
    format_duration_hms,
    format_duration_human,
    format_file_size
)

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("audiosplit.api")

# Application Configuration
TEMP_DIR = BASE_DIR / "temp_jobs"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Configuration from environment with robust defaults
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "500"))  # 500 MB default limit
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
JOB_RETENTION_SECONDS = int(os.environ.get("JOB_RETENTION_SECONDS", "3600"))  # 1 hour retention
CHUNK_SIZE = 1024 * 1024  # 1 MB stream chunk

SUPPORTED_MEDIA_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".oga",
    ".opus", ".mp4", ".mpeg", ".mpg", ".m4v", ".wma", ".webm"
}

DISALLOWED_DOCUMENT_EXTENSIONS = {
    ".txt", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".exe", ".bat", ".cmd", ".sh", ".zip", ".rar", ".7z", ".tar",
    ".gz", ".iso", ".dmg", ".html", ".htm", ".css", ".js", ".ts",
    ".json", ".xml", ".py", ".java", ".c", ".cpp", ".csv"
}

UUID_REGEX = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
SAFE_FILENAME_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]+$")

app = FastAPI(
    title="AudioSplit Pro API",
    description="Professional Audio Splitting Web API using FFmpeg",
    version="1.0.0"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory Job State Management with Thread Lock
jobs_db: Dict[str, Dict[str, Any]] = {}
jobs_lock = asyncio.Lock()


# Models
class SplitRequest(BaseModel):
    job_id: str = Field(..., description="UUID of the analyzed audio file")
    split_duration_minutes: float = Field(..., gt=0.05, le=1440.0, description="Desired split duration in minutes")


def sanitize_filename(filename: str) -> str:
    """
    Sanitize user-provided filename to prevent path traversal and shell issues,
    while safely preserving multiple extensions (e.g. .MP3.mpeg).
    """
    base = Path(filename).name
    # Keep alphanumeric, periods, dashes, underscores
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", base)
    cleaned = re.sub(r"_+", "_", cleaned)
    if not cleaned or cleaned.startswith("."):
        cleaned = f"audio_{int(time.time())}.mp3"
    return cleaned[:120]


def get_job_paths(job_id: str) -> Dict[str, Path]:
    """Return verified paths for a specific job."""
    if not UUID_REGEX.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job ID format.")
    job_dir = (TEMP_DIR / job_id).resolve()
    # Path traversal check
    if not job_dir.is_relative_to(TEMP_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid job path.")
    return {
        "job_dir": job_dir,
        "input_dir": job_dir / "input",
        "output_dir": job_dir / "output",
        "archive_dir": job_dir / "archive",
        "metadata_file": job_dir / "metadata.json"
    }


async def save_job_metadata(job_id: str):
    """Persist job metadata to disk."""
    if job_id in jobs_db:
        paths = get_job_paths(job_id)
        try:
            data = jobs_db[job_id].copy()
            # Omit non-serializable objects
            if "lock" in data:
                del data["lock"]
            with open(paths["metadata_file"], "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist metadata for job {job_id}: {e}")


async def load_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve job from memory or disk after validating job ID format."""
    if not UUID_REGEX.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job ID format.")

    if job_id in jobs_db:
        jobs_db[job_id]["last_accessed"] = time.time()
        return jobs_db[job_id]

    # Check on disk
    try:
        paths = get_job_paths(job_id)
        if paths["metadata_file"].exists():
            with open(paths["metadata_file"], "r", encoding="utf-8") as f:
                data = json.load(f)
                data["last_accessed"] = time.time()
                data["lock"] = asyncio.Lock()
                jobs_db[job_id] = data
                return data
    except HTTPException:
        raise
    except (OSError, json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Error reading job from disk: {e}")

    return None


# Background Audio Splitting Worker
async def process_audio_split_task(job_id: str, split_duration_minutes: float):
    """Background task executing the audio splitting and zip packaging."""
    job = jobs_db.get(job_id)
    if not job:
        logger.error(f"Cannot process splitting: job {job_id} not found in state.")
        return

    paths = get_job_paths(job_id)
    input_file = Path(job["source_file_path"])
    output_dir = paths["output_dir"]
    archive_dir = paths["archive_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    job["status"] = "processing"
    job["split_duration_minutes"] = split_duration_minutes
    job["current_status_message"] = "Preparing audio streams for splitting..."
    job["progress_percent"] = 5.0
    await save_job_metadata(job_id)

    try:
        metadata = job["metadata"]
        total_duration = metadata["duration_seconds"]
        split_duration_seconds = split_duration_minutes * 60.0

        # Calculate segments
        total_segments = max(1, math.ceil(total_duration / split_duration_seconds))
        job["total_segments"] = total_segments
        job["completed_segments"] = 0

        out_ext, encode_args, profile_desc = determine_output_profile(job["filename"], metadata)
        job["output_extension"] = out_ext
        job["processing_notes"] = profile_desc

        logger.info(f"Splitting job {job_id}: {total_segments} segments, profile: {profile_desc}")

        # Prepare segment task descriptors
        segment_tasks = []
        for seg_idx in range(1, total_segments + 1):
            start_sec = (seg_idx - 1) * split_duration_seconds
            is_last_segment = (seg_idx == total_segments)
            expected_dur = round(total_duration - start_sec, 2) if is_last_segment else split_duration_seconds
            duration_sec = None if is_last_segment else split_duration_seconds

            seg_filename = f"audio_part_{seg_idx:02d}.{out_ext}"
            seg_path = output_dir / seg_filename

            segment_tasks.append({
                "seg_idx": seg_idx,
                "start_sec": start_sec,
                "duration_sec": duration_sec,
                "expected_dur": expected_dur,
                "seg_filename": seg_filename,
                "seg_path": seg_path
            })

        # Worker function for parallel segment execution
        def run_single_segment(stask):
            success = execute_split_segment(
                input_file,
                stask["seg_path"],
                stask["start_sec"],
                stask["duration_sec"],
                encode_args
            )
            if not success:
                raise RuntimeError(f"FFmpeg failed while generating segment {stask['seg_idx']} ({stask['seg_filename']}).")

            valid, actual_dur, actual_size = verify_audio_file(
                stask["seg_path"],
                expected_duration=stask["expected_dur"]
            )
            if not valid or actual_size == 0:
                raise RuntimeError(f"Generated segment {stask['seg_filename']} is invalid or has 0 bytes.")

            return {
                "segment_number": stask["seg_idx"],
                "filename": stask["seg_filename"],
                "duration_seconds": round(actual_dur, 2),
                "formatted_duration": format_duration_hms(actual_dur),
                "file_size_bytes": actual_size,
                "formatted_size": format_file_size(actual_size),
                "download_url": f"/api/audio/jobs/{job_id}/download/{stask['seg_filename']}"
            }

        # Process segments with optimal worker concurrency
        max_workers = min(4, os.cpu_count() or 2, total_segments)
        completed_count = 0
        segments_meta_dict = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {executor.submit(run_single_segment, task): task for task in segment_tasks}
            for future in concurrent.futures.as_completed(future_to_task):
                seg_result = future.result()
                completed_count += 1
                segments_meta_dict[seg_result["segment_number"]] = seg_result

                job["completed_segments"] = completed_count
                # Scale progress cleanly from 10% to 88%
                progress_val = round(10.0 + (completed_count / total_segments) * 78.0, 1)
                job["progress_percent"] = progress_val
                job["current_status_message"] = f"Generated segment {completed_count} of {total_segments} ({progress_val}%)..."
                await save_job_metadata(job_id)

        # Sort segments in proper sequential order
        segments_meta = [segments_meta_dict[i] for i in sorted(segments_meta_dict.keys())]

        # Generate ZIP archive
        job["current_status_message"] = "Packaging audio segments into ZIP archive..."
        job["progress_percent"] = 92.0
        await save_job_metadata(job_id)

        clean_base = Path(job["filename"]).stem
        clean_base_safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean_base)[:30]
        zip_filename = f"{clean_base_safe}_split_parts.zip"
        zip_path = archive_dir / zip_filename

        segment_paths = [output_dir / s["filename"] for s in segments_meta]
        zip_size = await asyncio.to_thread(create_zip_archive, segment_paths, zip_path)

        job["segments"] = segments_meta
        job["zip_filename"] = zip_filename
        job["zip_path"] = str(zip_path)
        job["zip_size_bytes"] = zip_size
        job["formatted_zip_size"] = format_file_size(zip_size)
        job["zip_download_url"] = f"/api/audio/jobs/{job_id}/download-zip"

        job["status"] = "completed"
        job["progress_percent"] = 100.0
        job["current_status_message"] = f"Successfully generated {total_segments} audio segments."
        job["error"] = None
        await save_job_metadata(job_id)
        logger.info(f"Job {job_id} completed successfully with {total_segments} segments.")

    except Exception as e:
        logger.error(f"Job {job_id} encountered processing error: {e}", exc_info=True)
        job["status"] = "failed"
        job["error"] = str(e)
        job["current_status_message"] = f"Processing error: {str(e)}"
        await save_job_metadata(job_id)


# API Endpoints

@app.post("/api/audio/analyze")
async def analyze_audio(file: UploadFile = File(...)):
    """
    Upload and analyze an audio file.
    Streams upload to disk to handle large files efficiently.
    Uses FFprobe to detect duration, codecs, sample rate, channels.
    """
    if not file.filename or not file.filename.strip():
        raise HTTPException(status_code=400, detail="No file selected for upload.")

    original_filename = file.filename.strip()
    
    # Case-insensitive extension extraction supporting multiple extensions
    # e.g. "Audio_Part_1.MP3.mpeg" -> [".mp3", ".mpeg"]
    suffixes = [s.lower() for s in Path(original_filename).suffixes]
    final_ext = Path(original_filename).suffix.lower()
    has_media_ext = any(s in SUPPORTED_MEDIA_EXTENSIONS for s in suffixes)

    # Immediately reject obvious non-media documents/code if no media extension exists
    if final_ext and final_ext in DISALLOWED_DOCUMENT_EXTENSIONS and not has_media_ext:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{final_ext}'. AudioSplit Pro supports audio recordings (MP3, WAV, M4A, AAC, FLAC, OGG) and MP4 video."
        )

    job_id = str(uuid.uuid4())
    safe_name = sanitize_filename(original_filename)

    paths = get_job_paths(job_id)
    paths["input_dir"].mkdir(parents=True, exist_ok=True)
    destination_path = paths["input_dir"] / safe_name

    total_bytes = 0

    try:
        # Stream file to disk in chunks to avoid high RAM consumption
        with open(destination_path, "wb") as out_file:
            while chunk := await file.read(CHUNK_SIZE):
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_SIZE_BYTES:
                    out_file.close()
                    if destination_path.exists():
                        destination_path.unlink()
                    shutil.rmtree(paths["job_dir"], ignore_errors=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum allowed upload size of {MAX_UPLOAD_SIZE_MB} MB."
                    )
                out_file.write(chunk)

        if total_bytes == 0:
            shutil.rmtree(paths["job_dir"], ignore_errors=True)
            raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")

        # Analyze with FFprobe
        metadata = await asyncio.to_thread(inspect_audio_file, destination_path)

        # Store in state
        job_data = {
            "job_id": job_id,
            "filename": safe_name,
            "original_filename": original_filename,
            "source_file_path": str(destination_path),
            "file_size_bytes": total_bytes,
            "formatted_size": format_file_size(total_bytes),
            "duration_seconds": metadata["duration_seconds"],
            "formatted_duration": metadata["formatted_duration"],
            "human_duration": metadata["human_duration"],
            "status": "uploaded",
            "progress_percent": 0.0,
            "current_status_message": "Audio analyzed successfully. Ready for split settings.",
            "error": None,
            "metadata": metadata,
            "created_at": time.time(),
            "last_accessed": time.time(),
            "lock": asyncio.Lock(),
            "segments": [],
            "total_segments": 0,
            "completed_segments": 0
        }

        async with jobs_lock:
            jobs_db[job_id] = job_data

        await save_job_metadata(job_id)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "job_id": job_id,
                "filename": safe_name,
                "file_size_bytes": total_bytes,
                "formatted_size": format_file_size(total_bytes),
                "duration_seconds": metadata["duration_seconds"],
                "formatted_duration": metadata["formatted_duration"],
                "human_duration": metadata["human_duration"],
                "detected_format": metadata["container_format"],
                "codec": metadata["codec_name"],
                "sample_rate": metadata["sample_rate"],
                "channels": metadata["channels"],
                "channel_layout": metadata["channel_layout"],
                "bit_rate": metadata["bit_rate_kbps"],
                "is_video_container": metadata["is_video_container"],
                "available_split_options": [5, 10, 15, 20, 30]
            }
        )

    except HTTPException:
        raise
    except ValueError as val_err:
        shutil.rmtree(paths["job_dir"], ignore_errors=True)
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported or invalid file: {str(val_err)} Please upload a valid MP3, WAV, M4A, AAC, FLAC, OGG, or MP4 recording."
        )
    except Exception as e:
        shutil.rmtree(paths["job_dir"], ignore_errors=True)
        logger.error(f"Upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error processing audio file: {str(e)}")


@app.post("/api/audio/split")
async def start_split(request: SplitRequest, background_tasks: BackgroundTasks):
    """
    Start audio splitting for an analyzed upload.
    Prevents duplicate processing requests.
    """
    job = await load_job(request.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or has expired. Please re-upload your audio file.")

    async with job["lock"]:
        current_status = job.get("status")
        if current_status in ["processing", "queued", "completed"]:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "job_id": request.job_id,
                    "status": current_status,
                    "estimated_segments": job.get("total_segments", 1),
                    "message": f"Job is already {current_status}."
                }
            )

        duration = job["metadata"]["duration_seconds"]
        split_sec = request.split_duration_minutes * 60.0
        estimated_segments = max(1, math.ceil(duration / split_sec))

        job["status"] = "queued"
        job["split_duration_minutes"] = request.split_duration_minutes
        job["total_segments"] = estimated_segments
        job["completed_segments"] = 0
        job["progress_percent"] = 2.0
        job["current_status_message"] = "Job queued for background processing..."
        job["error"] = None
        await save_job_metadata(request.job_id)

    # Launch splitting in background
    background_tasks.add_task(process_audio_split_task, request.job_id, request.split_duration_minutes)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "job_id": request.job_id,
            "status": "queued",
            "estimated_segments": estimated_segments,
            "message": f"Splitting started. Estimated {estimated_segments} segment(s)."
        }
    )


@app.get("/api/audio/jobs/{job_id}")
async def get_job_status(job_id: str):
    """
    Return the current processing status, completed segment count, and progress.
    """
    job = await load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or has expired.")

    return {
        "job_id": job_id,
        "status": job["status"],
        "progress_percent": job.get("progress_percent", 0.0),
        "completed_segments": job.get("completed_segments", 0),
        "total_segments": job.get("total_segments", 0),
        "message": job.get("current_status_message", ""),
        "error": job.get("error")
    }


@app.get("/api/audio/jobs/{job_id}/results")
async def get_job_results(job_id: str):
    """
    Return completed output file metadata and individual download URLs.
    """
    job = await load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or has expired.")

    if job["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed yet (current status: {job['status']})."
        )

    return {
        "job_id": job_id,
        "source_filename": job["filename"],
        "total_duration": job["duration_seconds"],
        "formatted_total_duration": job["formatted_duration"],
        "split_duration_minutes": job.get("split_duration_minutes"),
        "total_segments": len(job.get("segments", [])),
        "segments": job.get("segments", []),
        "zip_filename": job.get("zip_filename"),
        "zip_size_bytes": job.get("zip_size_bytes", 0),
        "formatted_zip_size": job.get("formatted_zip_size", ""),
        "zip_download_url": job.get("zip_download_url")
    }


@app.get("/api/audio/jobs/{job_id}/download/{filename}")
async def download_segment(job_id: str, filename: str):
    """
    Download a single generated audio segment.
    Guarded with strict path traversal prevention.
    """
    if not SAFE_FILENAME_REGEX.match(filename) or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename specification.")

    paths = get_job_paths(job_id)
    file_path = (paths["output_dir"] / filename).resolve()

    if not file_path.is_relative_to(paths["output_dir"].resolve()) or not file_path.exists():
        raise HTTPException(status_code=404, detail="Requested audio segment not found.")

    # Determine media type
    ext = file_path.suffix.lower()
    media_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg"
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/audio/jobs/{job_id}/download-zip")
async def download_zip(job_id: str):
    """
    Download all generated segments as a single ZIP archive.
    """
    job = await load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or has expired.")

    paths = get_job_paths(job_id)
    zip_path = Path(job.get("zip_path", ""))

    if not zip_path.exists() or not zip_path.is_relative_to(paths["archive_dir"].resolve()):
        raise HTTPException(status_code=404, detail="ZIP archive not found or not yet generated.")

    zip_filename = job.get("zip_filename", f"audiosplit_{job_id[:8]}.zip")

    return FileResponse(
        path=zip_path,
        filename=zip_filename,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'}
    )


@app.delete("/api/audio/jobs/{job_id}")
async def delete_job(job_id: str):
    """
    Safely delete a job and all its temporary input and output files.
    """
    job = await load_job(job_id)
    paths = get_job_paths(job_id)

    if job and job.get("status") == "processing":
        raise HTTPException(
            status_code=409,
            detail="Cannot delete job while audio splitting is actively in progress."
        )

    # Remove from memory
    async with jobs_lock:
        if job_id in jobs_db:
            del jobs_db[job_id]

    # Delete directory tree
    if paths["job_dir"].exists():
        try:
            shutil.rmtree(paths["job_dir"], ignore_errors=True)
        except Exception as e:
            logger.error(f"Error removing job directory {paths['job_dir']}: {e}")
            raise HTTPException(status_code=500, detail="Failed to delete job storage directory.")

    return {"success": True, "message": "Job files successfully cleaned up."}


# Health Check
@app.get("/api/health")
async def health_check():
    """Health check endpoint to verify FFmpeg availability and server status."""
    return {
        "status": "healthy",
        "service": "AudioSplit Pro API",
        "ffmpeg_available": bool(FFMPEG_BIN and shutil.which(FFMPEG_BIN)),
        "ffprobe_available": bool(FFPROBE_BIN and shutil.which(FFPROBE_BIN)),
        "ffmpeg_path": FFMPEG_BIN,
        "max_upload_size_mb": MAX_UPLOAD_SIZE_MB,
        "retention_seconds": JOB_RETENTION_SECONDS
    }


# Automatic Expired Job Cleanup Background Task
async def periodic_cleanup_loop():
    """Background task running every 10 minutes to remove expired temporary jobs."""
    while True:
        try:
            await asyncio.sleep(600)  # Check every 10 minutes
            now = time.time()
            cutoff = now - JOB_RETENTION_SECONDS

            # Scan in-memory jobs
            expired_ids = []
            async with jobs_lock:
                for jid, jdata in list(jobs_db.items()):
                    if jdata.get("status") != "processing" and jdata.get("last_accessed", 0) < cutoff:
                        expired_ids.append(jid)
                for jid in expired_ids:
                    del jobs_db[jid]

            # Scan on-disk jobs
            if TEMP_DIR.exists():
                for sub in TEMP_DIR.iterdir():
                    if sub.is_dir() and UUID_REGEX.match(sub.name):
                        meta_file = sub / "metadata.json"
                        mtime = sub.stat().st_mtime
                        if mtime < cutoff:
                            # Verify not currently processing
                            if sub.name not in jobs_db or jobs_db[sub.name].get("status") != "processing":
                                logger.info(f"Auto-cleaning expired job directory: {sub.name}")
                                shutil.rmtree(sub, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Error in automatic cleanup loop: {e}")


@app.on_event("startup")
async def app_startup():
    """Start background cleaner on application startup."""
    asyncio.create_task(periodic_cleanup_loop())
    logger.info("AudioSplit Pro backend started successfully.")


# Mount Frontend Static Files if frontend directory exists
FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
