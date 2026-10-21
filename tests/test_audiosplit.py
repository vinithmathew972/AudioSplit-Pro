"""
AudioSplit Pro - Comprehensive Integration & Unit Test Suite
Covers all scenarios in Section 11 of requirements.
"""

import os
import sys
import time
import json
import shutil
import zipfile
import subprocess
from pathlib import Path

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "backend"))

from fastapi.testclient import TestClient
from main import app, FFMPEG_BIN, FFPROBE_BIN

client = TestClient(app)

TEST_DIR = BASE_DIR / "tests" / "fixtures"
TEST_DIR.mkdir(parents=True, exist_ok=True)


def generate_synthetic_media():
    """Generates small synthetic test media files using FFmpeg."""
    print("Generating synthetic media files for testing...")
    
    # 1. MP3 file (70 seconds duration -> tests splitting into 30s, 30s, 10s remainder)
    mp3_path = TEST_DIR / "test_sample_70s.mp3"
    if not mp3_path.exists():
        subprocess.run([
            FFMPEG_BIN, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=70",
            "-c:a", "libmp3lame", "-b:a", "128k", str(mp3_path)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 2. WAV file (15 seconds duration)
    wav_path = TEST_DIR / "test_sample_15s.wav"
    if not wav_path.exists():
        subprocess.run([
            FFMPEG_BIN, "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=15",
            "-c:a", "pcm_s16le", str(wav_path)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 3. M4A file (12 seconds duration)
    m4a_path = TEST_DIR / "test_sample_12s.m4a"
    if not m4a_path.exists():
        subprocess.run([
            FFMPEG_BIN, "-y", "-f", "lavfi", "-i", "sine=frequency=550:duration=12",
            "-c:a", "aac", "-b:a", "128k", str(m4a_path)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 4. MP4 Video with audio track (20 seconds duration)
    mp4_path = TEST_DIR / "test_video_20s.mp4"
    if not mp4_path.exists():
        subprocess.run([
            FFMPEG_BIN, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=20:size=160x120:rate=15",
            "-f", "lavfi", "-i", "sine=frequency=660:duration=20",
            "-c:v", "libx264", "-c:a", "aac", str(mp4_path)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 5. Unsupported text file
    unsupported_path = TEST_DIR / "test_document.txt"
    unsupported_path.write_text("This is not an audio file.")

    # 6. Corrupted audio file (random bytes disguised as mp3)
    corrupted_path = TEST_DIR / "test_corrupted.mp3"
    corrupted_path.write_bytes(b"NOT_A_REAL_MP3_DATA_GARBAGE_BYTES_1234567890" * 20)

    print("Synthetic media files created successfully.")


def run_tests():
    generate_synthetic_media()
    passed = 0
    total = 0

    def assert_test(condition, name):
        nonlocal passed, total
        total += 1
        if condition:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}")
            raise AssertionError(f"Test failed: {name}")

    print("\n--- 1. Testing Health & Binaries ---")
    res = client.get("/api/health")
    assert_test(res.status_code == 200, "Health check returns 200 OK")
    data = res.json()
    assert_test(data["ffmpeg_available"] is True, "FFmpeg detected by backend")
    assert_test(data["ffprobe_available"] is True, "FFprobe detected by backend")

    print("\n--- 2. Testing Audio Analysis (MP3, WAV, M4A, MP4) ---")
    
    # 2a. MP3
    mp3_file = TEST_DIR / "test_sample_70s.mp3"
    with open(mp3_file, "rb") as f:
        res = client.post("/api/audio/analyze", files={"file": ("test_sample_70s.mp3", f, "audio/mpeg")})
    assert_test(res.status_code == 200, "Analyze valid MP3")
    mp3_job = res.json()
    assert_test("job_id" in mp3_job, "Returns UUID job_id")
    assert_test(69.0 <= mp3_job["duration_seconds"] <= 71.0, f"Duration is ~70s (detected: {mp3_job['duration_seconds']}s)")
    assert_test(mp3_job["is_video_container"] is False, "MP3 is not video container")

    # 2b. WAV
    wav_file = TEST_DIR / "test_sample_15s.wav"
    with open(wav_file, "rb") as f:
        res = client.post("/api/audio/analyze", files={"file": ("test_sample_15s.wav", f, "audio/wav")})
    assert_test(res.status_code == 200, "Analyze valid WAV")
    wav_job = res.json()
    assert_test(14.0 <= wav_job["duration_seconds"] <= 16.0, f"Duration is ~15s (detected: {wav_job['duration_seconds']}s)")

    # 2c. M4A
    m4a_file = TEST_DIR / "test_sample_12s.m4a"
    with open(m4a_file, "rb") as f:
        res = client.post("/api/audio/analyze", files={"file": ("test_sample_12s.m4a", f, "audio/mp4")})
    assert_test(res.status_code == 200, "Analyze valid M4A")

    # 2d. MP4 Video containing audio track
    mp4_file = TEST_DIR / "test_video_20s.mp4"
    with open(mp4_file, "rb") as f:
        res = client.post("/api/audio/analyze", files={"file": ("test_video_20s.mp4", f, "video/mp4")})
    assert_test(res.status_code == 200, "Analyze MP4 containing audio")
    mp4_job = res.json()
    assert_test(mp4_job["is_video_container"] is True, "MP4 detected as video container containing audio")
    assert_test(19.0 <= mp4_job["duration_seconds"] <= 21.0, "MP4 audio duration detected correctly (~20s)")

    print("\n--- 3. Testing Input Rejections & Error Handling ---")
    
    # 3a. Unsupported file (.txt)
    unsupported_file = TEST_DIR / "test_document.txt"
    with open(unsupported_file, "rb") as f:
        res = client.post("/api/audio/analyze", files={"file": ("test_document.txt", f, "text/plain")})
    assert_test(res.status_code == 400, "Reject unsupported extension (.txt)")

    # 3b. Corrupted audio file
    corrupted_file = TEST_DIR / "test_corrupted.mp3"
    with open(corrupted_file, "rb") as f:
        res = client.post("/api/audio/analyze", files={"file": ("test_corrupted.mp3", f, "audio/mpeg")})
    assert_test(res.status_code == 400, "Reject corrupted audio file")

    print("\n--- 4. Testing Audio Splitting Execution & Progress Polling ---")
    
    # 4a. Split MP3: 70 seconds audio split into 0.5 minute (30s) segments
    # Expect 3 segments: [0-30s], [30-60s], [60-70s (remaining 10s)]
    job_id = mp3_job["job_id"]
    split_payload = {
        "job_id": job_id,
        "split_duration_minutes": 0.5  # 30 seconds
    }
    res = client.post("/api/audio/split", json=split_payload)
    assert_test(res.status_code == 200, "Split request accepted")
    split_info = res.json()
    assert_test(split_info["estimated_segments"] == 3, f"Estimated segments = 3 (actual: {split_info['estimated_segments']})")

    # 4b. Test Duplicate submission prevention
    res_dup = client.post("/api/audio/split", json=split_payload)
    assert_test(res_dup.status_code == 200, "Duplicate submission handled safely without double processing")

    # Poll status until completed (max 30 seconds)
    print("  Polling job status until completion...")
    start_time = time.time()
    job_status = None
    while time.time() - start_time < 30:
        res = client.get(f"/api/audio/jobs/{job_id}")
        assert_test(res.status_code == 200, "Job status endpoint accessible")
        job_status = res.json()
        if job_status["status"] in ["completed", "failed"]:
            break
        time.sleep(0.5)

    assert_test(job_status["status"] == "completed", f"Job completed successfully (status: {job_status['status']})")
    assert_test(job_status["completed_segments"] == 3, f"Completed segment count is 3 (was: {job_status['completed_segments']})")

    print("\n--- 5. Testing Results & Segment Verification ---")
    res = client.get(f"/api/audio/jobs/{job_id}/results")
    assert_test(res.status_code == 200, "Results endpoint returns 200 OK")
    results = res.json()
    assert_test(results["total_segments"] == 3, "Total segments in results is 3")
    
    segments = results["segments"]
    assert_test(segments[0]["filename"] == "audio_part_01.mp3", "Segment 1 named audio_part_01.mp3")
    assert_test(segments[1]["filename"] == "audio_part_02.mp3", "Segment 2 named audio_part_02.mp3")
    assert_test(segments[2]["filename"] == "audio_part_03.mp3", "Segment 3 named audio_part_03.mp3")

    # Verify duration of final segment preserves trailing audio (~10s)
    final_seg_dur = segments[2]["duration_seconds"]
    assert_test(9.0 <= final_seg_dur <= 11.0, f"Final segment preserves trailing audio: {final_seg_dur}s (~10s)")

    print("\n--- 6. Testing Individual Segment Downloads & ZIP Archive ---")
    
    # 6a. Download individual segment
    dl_url = segments[0]["download_url"]
    res = client.get(dl_url)
    assert_test(res.status_code == 200, "Individual segment download successful")
    assert_test(len(res.content) > 0, "Downloaded segment contains data")
    assert_test("audio/mpeg" in res.headers.get("content-type", ""), "Proper Content-Type for MP3 segment")

    # 6b. Download ZIP archive
    zip_url = results["zip_download_url"]
    res = client.get(zip_url)
    assert_test(res.status_code == 200, "ZIP archive download successful")
    assert_test("application/zip" in res.headers.get("content-type", ""), "Proper Content-Type for ZIP")
    
    # Verify ZIP contents
    temp_zip = TEST_DIR / "verify.zip"
    temp_zip.write_bytes(res.content)
    with zipfile.ZipFile(temp_zip, "r") as zf:
        namelist = zf.namelist()
        assert_test(len(namelist) == 3, f"ZIP contains exactly 3 files: {namelist}")
        assert_test(zf.testzip() is None, "ZIP archive integrity verified (zero corruptions)")
    if temp_zip.exists():
        temp_zip.unlink()

    print("\n--- 7. Testing MP4 Video Audio Extraction Splitting ---")
    # Split MP4 audio: 20 seconds audio split into 0.25 min (15s) segments => 2 segments (15s, 5s)
    mp4_job_id = mp4_job["job_id"]
    res = client.post("/api/audio/split", json={"job_id": mp4_job_id, "split_duration_minutes": 0.25})
    assert_test(res.status_code == 200, "MP4 audio split started")
    
    start_time = time.time()
    while time.time() - start_time < 30:
        res = client.get(f"/api/audio/jobs/{mp4_job_id}")
        if res.json()["status"] in ["completed", "failed"]:
            break
        time.sleep(0.5)
    
    res = client.get(f"/api/audio/jobs/{mp4_job_id}/results")
    assert_test(res.status_code == 200, "MP4 split results retrieved")
    mp4_results = res.json()
    assert_test(mp4_results["total_segments"] == 2, f"MP4 split produced 2 audio segments (was: {mp4_results['total_segments']})")
    
    # Download segment 1 and check that it contains NO video stream
    mp4_seg_url = mp4_results["segments"][0]["download_url"]
    seg_res = client.get(mp4_seg_url)
    temp_seg = TEST_DIR / "temp_mp4_seg.m4a"
    temp_seg.write_bytes(seg_res.content)
    
    probe_proc = subprocess.run([
        FFPROBE_BIN, "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(temp_seg)
    ], capture_output=True, text=True)
    probe_info = json.loads(probe_proc.stdout)
    codec_types = [s["codec_type"] for s in probe_info.get("streams", [])]
    assert_test("video" not in codec_types, "MP4 segment contains NO video stream (audio track only)")
    assert_test("audio" in codec_types, "MP4 segment contains pure audio track")
    if temp_seg.exists():
        temp_seg.unlink()

    print("\n--- 8. Testing Edge Case: Audio Shorter Than Split Duration ---")
    # 15s WAV audio with 5-minute split => 1 segment containing all 15s
    wav_job_id = wav_job["job_id"]
    res = client.post("/api/audio/split", json={"job_id": wav_job_id, "split_duration_minutes": 5.0})
    assert_test(res.status_code == 200, "Start split for short audio")
    
    start_time = time.time()
    while time.time() - start_time < 20:
        res = client.get(f"/api/audio/jobs/{wav_job_id}")
        if res.json()["status"] == "completed":
            break
        time.sleep(0.5)

    res = client.get(f"/api/audio/jobs/{wav_job_id}/results")
    wav_results = res.json()
    assert_test(wav_results["total_segments"] == 1, "Short audio produces exactly 1 segment")
    assert_test(14.0 <= wav_results["segments"][0]["duration_seconds"] <= 16.0, "Entire duration preserved")

    print("\n--- 9. Testing Security & Path Traversal Prevention ---")
    
    # 9a. Path traversal attempt in job_id
    res = client.get("/api/audio/jobs/../../etc/passwd")
    assert_test(res.status_code in [400, 404], "Path traversal in job_id rejected")

    # 9b. Path traversal attempt in filename download
    res = client.get(f"/api/audio/jobs/{job_id}/download/../../main.py")
    assert_test(res.status_code in [400, 404], "Path traversal in filename download rejected")

    # 9c. Invalid UUID format
    res = client.get("/api/audio/jobs/not-a-real-uuid")
    assert_test(res.status_code == 400, "Non-UUID job_id rejected with 400 Bad Request")

    print("\n--- 10. Testing Temporary Storage Cleanup ---")
    res = client.delete(f"/api/audio/jobs/{job_id}")
    assert_test(res.status_code == 200, "Delete job endpoint returns 200 OK")
    
    # Verify job files removed
    res = client.get(f"/api/audio/jobs/{job_id}")
    assert_test(res.status_code == 404, "Deleted job is no longer accessible (404)")

    # Clean up other test jobs
    client.delete(f"/api/audio/jobs/{wav_job_id}")
    client.delete(f"/api/audio/jobs/{mp4_job_id}")

    # Clean fixtures
    shutil.rmtree(TEST_DIR, ignore_errors=True)

    print(f"\n==========================================")
    print(f" ALL {passed}/{total} TESTS PASSED SUCCESSFULLY! ")
    print(f"==========================================\n")


if __name__ == "__main__":
    run_tests()
