"""
Test for long recordings (60 minutes & 120 minutes).
Verifies:
6. Split a 60-minute audio file into 30-minute segments (2 segments).
7. Split a 120-minute audio file into 20-minute segments (6 segments).
"""

import sys
import time
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "backend"))

from fastapi.testclient import TestClient
from main import app, FFMPEG_BIN, FFPROBE_BIN

client = TestClient(app)
FIXTURE_DIR = BASE_DIR / "tests" / "fixtures_long"
FIXTURE_DIR.mkdir(parents=True, exist_ok=True)


def test_60_and_120_minute_audio():
    print("Testing 60-minute and 120-minute audio splitting...")

    # 1. Generate 60-minute lightweight audio (anullsrc generates in ~1 second)
    file_60m = FIXTURE_DIR / "audio_60min.mp3"
    print("  Creating 60-minute audio (3600 seconds)...")
    subprocess.run([
        FFMPEG_BIN, "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
        "-t", "3600", "-c:a", "libmp3lame", "-b:a", "32k", str(file_60m)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 2. Generate 120-minute lightweight audio (7200 seconds)
    file_120m = FIXTURE_DIR / "audio_120min.mp3"
    print("  Creating 120-minute audio (7200 seconds)...")
    subprocess.run([
        FFMPEG_BIN, "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
        "-t", "7200", "-c:a", "libmp3lame", "-b:a", "32k", str(file_120m)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Test 6: 60-minute split into 30-minute segments
    print("\n--- Test Scenario 6: 60-minute audio into 30-minute segments ---")
    with open(file_60m, "rb") as f:
        res = client.post("/api/audio/analyze", files={"file": ("audio_60min.mp3", f, "audio/mpeg")})
    assert res.status_code == 200, f"Analyze 60m audio failed: {res.text}"
    job_60 = res.json()
    job_id_60 = job_60["job_id"]
    print(f"  Analyzed duration: {job_60['formatted_duration']} ({job_60['duration_seconds']}s)")
    assert 3590 <= job_60["duration_seconds"] <= 3610

    # Start split: 30 minutes
    res = client.post("/api/audio/split", json={"job_id": job_id_60, "split_duration_minutes": 30.0})
    assert res.status_code == 200
    assert res.json()["estimated_segments"] == 2

    # Await completion
    start = time.time()
    while time.time() - start < 60:
        res = client.get(f"/api/audio/jobs/{job_id_60}")
        if res.json()["status"] == "completed":
            break
        time.sleep(1)

    res = client.get(f"/api/audio/jobs/{job_id_60}/results")
    assert res.status_code == 200
    res_60 = res.json()
    assert res_60["total_segments"] == 2, f"Expected 2 segments, got {res_60['total_segments']}"
    print(f"  [PASS] 60-minute split into exactly 2 segments: {[s['filename'] for s in res_60['segments']]}")
    for seg in res_60["segments"]:
        print(f"    - {seg['filename']}: duration {seg['formatted_duration']} ({seg['duration_seconds']}s), size: {seg['formatted_size']}")
    
    # Clean up 60m job
    client.delete(f"/api/audio/jobs/{job_id_60}")

    # Test 7: 120-minute split into 20-minute segments
    print("\n--- Test Scenario 7: 120-minute audio into 20-minute segments ---")
    with open(file_120m, "rb") as f:
        res = client.post("/api/audio/analyze", files={"file": ("audio_120min.mp3", f, "audio/mpeg")})
    assert res.status_code == 200, f"Analyze 120m audio failed: {res.text}"
    job_120 = res.json()
    job_id_120 = job_120["job_id"]
    print(f"  Analyzed duration: {job_120['formatted_duration']} ({job_120['duration_seconds']}s)")
    assert 7190 <= job_120["duration_seconds"] <= 7210

    # Start split: 20 minutes => 120 / 20 = 6 segments
    res = client.post("/api/audio/split", json={"job_id": job_id_120, "split_duration_minutes": 20.0})
    assert res.status_code == 200
    assert res.json()["estimated_segments"] == 6

    # Await completion
    start = time.time()
    while time.time() - start < 90:
        res = client.get(f"/api/audio/jobs/{job_id_120}")
        if res.json()["status"] == "completed":
            break
        time.sleep(1)

    res = client.get(f"/api/audio/jobs/{job_id_120}/results")
    assert res.status_code == 200
    res_120 = res.json()
    assert res_120["total_segments"] == 6, f"Expected 6 segments, got {res_120['total_segments']}"
    print(f"  [PASS] 120-minute split into exactly 6 segments: {[s['filename'] for s in res_120['segments']]}")
    for seg in res_120["segments"]:
        print(f"    - {seg['filename']}: duration {seg['formatted_duration']} ({seg['duration_seconds']}s), size: {seg['formatted_size']}")

    # Clean up 120m job
    client.delete(f"/api/audio/jobs/{job_id_120}")

    import shutil
    shutil.rmtree(FIXTURE_DIR, ignore_errors=True)
    print("\n==================================================")
    print(" 60-MINUTE & 120-MINUTE SPLIT TESTS PASSED! ")
    print("==================================================")


if __name__ == "__main__":
    test_60_and_120_minute_audio()
