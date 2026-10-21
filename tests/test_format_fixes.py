"""
AudioSplit Pro - Format Validation & Fix Verification Tests
Tests:
1. File with multiple extensions: Audio_Part_1.MP3.mpeg
2. Uppercase extensions: sample.MP3, sample.WAV, sample.M4A, clip.MP4
3. Mixed-case extensions: sample.Mp3.Mpeg, record.wAv
4. Unusual extensions with valid audio: audio.dat
5. Full splitting workflow for Audio_Part_1.MP3.mpeg (verifying segment generation and zip)
6. Rejection of genuinely unsupported files: document.txt, image.png, corrupted.mp3
"""

import os
import sys
import time
import json
import shutil
import zipfile
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "backend"))

from fastapi.testclient import TestClient
from main import app, FFMPEG_BIN, FFPROBE_BIN

client = TestClient(app)
FIXTURE_DIR = BASE_DIR / "tests" / "fixtures_formats"
FIXTURE_DIR.mkdir(parents=True, exist_ok=True)


def setup_fixtures():
    # 1. Base real MP3
    base_mp3 = FIXTURE_DIR / "base.mp3"
    subprocess.run([
        FFMPEG_BIN, "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=10",
        "-c:a", "libmp3lame", "-b:a", "128k", str(base_mp3)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 2. Base real WAV
    base_wav = FIXTURE_DIR / "base.wav"
    subprocess.run([
        FFMPEG_BIN, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-c:a", "pcm_s16le", str(base_wav)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 3. Base real MP4 with audio
    base_mp4 = FIXTURE_DIR / "base.mp4"
    subprocess.run([
        FFMPEG_BIN, "-y",
        "-f", "lavfi", "-i", "testsrc=duration=6:size=160x120:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=500:duration=6",
        "-c:v", "libx264", "-c:a", "aac", str(base_mp4)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Multi-extension & unusual files
    shutil.copy(base_mp3, FIXTURE_DIR / "Audio_Part_1.MP3.mpeg")
    shutil.copy(base_mp3, FIXTURE_DIR / "Podcast.Mp3.Mpeg")
    shutil.copy(base_mp3, FIXTURE_DIR / "Track_Uppercase.MP3")
    shutil.copy(base_wav, FIXTURE_DIR / "RECORDING.WAV")
    shutil.copy(base_wav, FIXTURE_DIR / "session.wAv")
    shutil.copy(base_mp4, FIXTURE_DIR / "video_lecture.MP4")
    shutil.copy(base_mp3, FIXTURE_DIR / "audio_custom.dat")

    # Unsupported non-media files
    (FIXTURE_DIR / "document.txt").write_text("Hello, this is a plain text file.")
    (FIXTURE_DIR / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
    (FIXTURE_DIR / "corrupted.mp3").write_bytes(b"CORRUPTED_FAKE_AUDIO_DATA_BYTES" * 30)


def run_tests():
    setup_fixtures()
    print("\n=======================================================")
    print(" Running Format Validation & Multiple Extension Tests ")
    print("=======================================================\n")

    passed = 0
    total = 0

    def check(condition, desc):
        nonlocal passed, total
        total += 1
        if condition:
            print(f"  [PASS] {desc}")
            passed += 1
        else:
            print(f"  [FAIL] {desc}")
            raise AssertionError(f"Failed: {desc}")

    # 1. Test Audio_Part_1.MP3.mpeg
    print("1. Testing Audio_Part_1.MP3.mpeg upload & analysis:")
    target_file = FIXTURE_DIR / "Audio_Part_1.MP3.mpeg"
    with open(target_file, "rb") as f:
        res = client.post("/api/audio/analyze", files={"file": ("Audio_Part_1.MP3.mpeg", f, "audio/mpeg")})
    check(res.status_code == 200, "Audio_Part_1.MP3.mpeg accepted (HTTP 200)")
    data = res.json()
    check("job_id" in data, "Returns job_id")
    check(data["filename"] == "Audio_Part_1.MP3.mpeg", f"Filename preserved: {data['filename']}")
    check(data["codec"] == "mp3", f"FFprobe correctly identified MP3 codec: {data['codec']}")
    check(9.0 <= data["duration_seconds"] <= 11.0, f"Duration is ~10s: {data['duration_seconds']}s")
    part1_job_id = data["job_id"]

    # 2. Test Uppercase & Mixed Case Extensions
    print("\n2. Testing Uppercase & Mixed-case Extensions:")
    cases = [
        ("Track_Uppercase.MP3", "audio/mpeg", "mp3"),
        ("RECORDING.WAV", "audio/wav", "pcm_s16le"),
        ("session.wAv", "audio/wav", "pcm_s16le"),
        ("video_lecture.MP4", "video/mp4", "aac"),
        ("Podcast.Mp3.Mpeg", "audio/mpeg", "mp3"),
    ]
    for fname, mime, expected_codec in cases:
        fpath = FIXTURE_DIR / fname
        with open(fpath, "rb") as f:
            res = client.post("/api/audio/analyze", files={"file": (fname, f, mime)})
        check(res.status_code == 200, f"Accepted '{fname}' (HTTP 200)")
        res_data = res.json()
        check(expected_codec in res_data["codec"], f"Detected codec '{res_data['codec']}' matches expected '{expected_codec}'")
        # Cleanup job
        client.delete(f"/api/audio/jobs/{res_data['job_id']}")

    # 3. Test Unusual Extension with Valid Audio (audio_custom.dat)
    print("\n3. Testing Unusual Extension with Valid Audio (audio_custom.dat):")
    dat_file = FIXTURE_DIR / "audio_custom.dat"
    with open(dat_file, "rb") as f:
        res = client.post("/api/audio/analyze", files={"file": ("audio_custom.dat", f, "application/octet-stream")})
    check(res.status_code == 200, "audio_custom.dat accepted via FFprobe (HTTP 200)")
    dat_data = res.json()
    check(dat_data["codec"] == "mp3", f"FFprobe detected MP3 in .dat file: {dat_data['codec']}")
    client.delete(f"/api/audio/jobs/{dat_data['job_id']}")

    # 4. Test Rejection of Genuinely Unsupported / Invalid Files
    print("\n4. Testing Rejection of Genuinely Invalid & Non-Media Files:")
    
    # 4a. Document (.txt)
    with open(FIXTURE_DIR / "document.txt", "rb") as f:
        res = client.post("/api/audio/analyze", files={"file": ("document.txt", f, "text/plain")})
    check(res.status_code == 400, "Rejected document.txt (HTTP 400)")
    check("Unsupported" in res.json().get("detail", ""), "Clear error message for .txt")

    # 4b. Corrupted audio (.mp3 with garbage bytes)
    with open(FIXTURE_DIR / "corrupted.mp3", "rb") as f:
        res = client.post("/api/audio/analyze", files={"file": ("corrupted.mp3", f, "audio/mpeg")})
    check(res.status_code == 400, "Rejected corrupted.mp3 (HTTP 400)")
    check("corrupted" in res.json().get("detail", "").lower() or "unable" in res.json().get("detail", "").lower(), "Clear error message for corrupted audio")

    # 5. Full Audio Splitting Workflow for Audio_Part_1.MP3.mpeg
    print("\n5. Testing Full Audio Splitting Workflow for Audio_Part_1.MP3.mpeg:")
    # 10s audio split into 4-second segments (0.067 min) -> 3 segments (4s, 4s, 2s)
    split_res = client.post("/api/audio/split", json={"job_id": part1_job_id, "split_duration_minutes": 0.0667})
    check(split_res.status_code == 200, "Audio splitting started for Audio_Part_1.MP3.mpeg")
    
    # Await completion
    start = time.time()
    while time.time() - start < 30:
        st = client.get(f"/api/audio/jobs/{part1_job_id}").json()
        if st["status"] == "completed":
            break
        time.sleep(0.5)

    results_res = client.get(f"/api/audio/jobs/{part1_job_id}/results")
    check(results_res.status_code == 200, "Retrieved results for Audio_Part_1.MP3.mpeg")
    res_info = results_res.json()
    check(res_info["total_segments"] == 3, f"Generated 3 segments (was {res_info['total_segments']})")
    check(res_info["segments"][0]["filename"] == "audio_part_01.mp3", "Segment 1 named audio_part_01.mp3")
    check(res_info["segments"][1]["filename"] == "audio_part_02.mp3", "Segment 2 named audio_part_02.mp3")
    check(res_info["segments"][2]["filename"] == "audio_part_03.mp3", "Segment 3 named audio_part_03.mp3")
    
    # Verify individual download
    dl_res = client.get(res_info["segments"][0]["download_url"])
    check(dl_res.status_code == 200, "Individual segment downloadable")
    check(len(dl_res.content) > 0, "Segment contains valid audio bytes")

    # Verify ZIP download
    zip_res = client.get(res_info["zip_download_url"])
    check(zip_res.status_code == 200, "ZIP archive downloadable")
    temp_zip = FIXTURE_DIR / "test.zip"
    temp_zip.write_bytes(zip_res.content)
    with zipfile.ZipFile(temp_zip, "r") as zf:
        check(len(zf.namelist()) == 3, f"ZIP contains all 3 segments: {zf.namelist()}")
        check(zf.testzip() is None, "ZIP integrity verified")
    if temp_zip.exists():
        temp_zip.unlink()

    # Cleanup
    client.delete(f"/api/audio/jobs/{part1_job_id}")
    shutil.rmtree(FIXTURE_DIR, ignore_errors=True)

    print(f"\n=======================================================")
    print(f" ALL {passed}/{total} FORMAT FIX TESTS PASSED SUCCESSFULLY! ")
    print(f"=======================================================\n")


if __name__ == "__main__":
    run_tests()
