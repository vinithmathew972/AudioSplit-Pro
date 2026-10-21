"""
AudioSplit Pro - Audio Processing Engine
Powered by FFmpeg & FFprobe
"""

import os
import sys
import json
import math
import shutil
import logging
import zipfile
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("audiosplit.processor")
logging.basicConfig(level=logging.INFO)

# Configurable timeouts
FFPROBE_TIMEOUT_SECONDS = 30
SEGMENT_TIMEOUT_SECONDS = 300  # 5 minutes per segment


def find_ffmpeg_binaries() -> Tuple[str, str]:
    """
    Locates ffmpeg and ffprobe binaries.
    Searches system PATH, refreshed environment PATH, and known Windows Winget/system locations.
    Raises RuntimeError if neither is found.
    """
    ffmpeg_cmd = shutil.which("ffmpeg")
    ffprobe_cmd = shutil.which("ffprobe")

    if ffmpeg_cmd and ffprobe_cmd:
        return ffmpeg_cmd, ffprobe_cmd

    # Refresh PATH from registry on Windows
    if sys.platform == "win32":
        try:
            import winreg
            paths = []
            for hkey, subkey in [
                (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                (winreg.HKEY_CURRENT_USER, r"Environment")
            ]:
                try:
                    with winreg.OpenKey(hkey, subkey) as key:
                        val, _ = winreg.QueryValueEx(key, "Path")
                        paths.extend(val.split(";"))
                except Exception:
                    pass

            # Search Winget directory directly
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            if local_appdata:
                winget_pkg_dir = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
                if winget_pkg_dir.exists():
                    for match in winget_pkg_dir.glob("**/ffmpeg.exe"):
                        bin_dir = match.parent
                        paths.append(str(bin_dir))

            # Additional common paths
            program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
            paths.extend([
                r"C:\ffmpeg\bin",
                str(Path(program_files) / "ffmpeg" / "bin"),
            ])

            for p in paths:
                p_clean = p.strip().strip('"')
                if not p_clean:
                    continue
                ff_candidate = Path(p_clean) / "ffmpeg.exe"
                fp_candidate = Path(p_clean) / "ffprobe.exe"
                if ff_candidate.exists() and fp_candidate.exists():
                    os.environ["PATH"] = p_clean + os.pathsep + os.environ.get("PATH", "")
                    return str(ff_candidate), str(fp_candidate)
        except Exception as e:
            logger.warning(f"Error while searching for ffmpeg in registry/known paths: {e}")

    # Final check
    ffmpeg_cmd = shutil.which("ffmpeg")
    ffprobe_cmd = shutil.which("ffprobe")
    if not ffmpeg_cmd or not ffprobe_cmd:
        raise RuntimeError(
            "FFmpeg and FFprobe binaries were not found. "
            "Please ensure FFmpeg is installed and accessible in the system PATH."
        )

    return ffmpeg_cmd, ffprobe_cmd


# Cache resolved binary paths
try:
    FFMPEG_BIN, FFPROBE_BIN = find_ffmpeg_binaries()
    logger.info(f"Using FFmpeg: {FFMPEG_BIN}")
    logger.info(f"Using FFprobe: {FFPROBE_BIN}")
except Exception as err:
    FFMPEG_BIN, FFPROBE_BIN = "ffmpeg", "ffprobe"
    logger.warning(f"FFmpeg not immediately resolved: {err}")


def format_duration_hms(seconds: float) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    if seconds < 0:
        return "00:00"
    total_sec = int(round(seconds))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_duration_human(seconds: float) -> str:
    """Format seconds into human readable text (e.g., '1 hr 25 min 10 sec')."""
    if seconds < 0:
        return "0 sec"
    total_sec = int(round(seconds))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours} hr" if hours == 1 else f"{hours} hrs")
    if minutes > 0:
        parts.append(f"{minutes} min")
    if secs > 0 or not parts:
        parts.append(f"{secs} sec")
    return " ".join(parts)


def format_file_size(bytes_count: int) -> str:
    """Format file size in bytes to B, KB, MB, GB."""
    if bytes_count < 1024:
        return f"{bytes_count} B"
    elif bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.1f} KB"
    elif bytes_count < 1024 * 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.2f} MB"
    else:
        return f"{bytes_count / (1024 * 1024 * 1024):.2f} GB"


def inspect_audio_file(file_path: Path) -> Dict[str, Any]:
    """
    Uses FFprobe to inspect an audio/video file.
    Extracts duration, format, audio stream codecs, sample rate, channels, bit rate.
    Raises ValueError on invalid or unreadable files, or if no audio track exists.
    """
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise ValueError("The provided file is empty or does not exist.")

    cmd = [
        FFPROBE_BIN,
        "-v", "error",
        "-show_entries", "format=duration,format_name,size,bit_rate",
        "-show_entries", "stream=index,codec_name,codec_type,sample_rate,channels,channel_layout,bit_rate,duration",
        "-of", "json",
        str(file_path)
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=FFPROBE_TIMEOUT_SECONDS,
            check=False
        )
    except subprocess.TimeoutExpired:
        raise ValueError("FFprobe timed out while analyzing the audio file.")
    except Exception as e:
        raise ValueError(f"Failed to execute FFprobe: {str(e)}")

    if result.returncode != 0:
        err_msg = result.stderr.strip() or "Corrupted or unsupported media file."
        raise ValueError(f"Unable to read audio file: {err_msg}")

    try:
        probe_data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise ValueError("Failed to parse audio metadata from FFprobe.")

    format_info = probe_data.get("format", {})
    streams = probe_data.get("streams", [])

    # Filter audio streams
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if not audio_streams:
        raise ValueError("No audio stream detected. The file contains no playable audio.")

    primary_stream = audio_streams[0]

    # Calculate duration
    duration = 0.0
    if "duration" in format_info and format_info["duration"]:
        try:
            duration = float(format_info["duration"])
        except ValueError:
            pass

    if duration <= 0.0 and "duration" in primary_stream and primary_stream["duration"]:
        try:
            duration = float(primary_stream["duration"])
        except ValueError:
            pass

    if duration <= 0.0:
        raise ValueError("Unable to determine valid audio duration. File may be corrupted.")

    file_size = file_path.stat().st_size
    codec_name = primary_stream.get("codec_name", "unknown")
    sample_rate = primary_stream.get("sample_rate", "unknown")
    channels = primary_stream.get("channels", 2)
    channel_layout = primary_stream.get("channel_layout", "stereo" if channels == 2 else "mono")
    container_format = format_info.get("format_name", "unknown")

    # Bitrate calculation
    bit_rate = format_info.get("bit_rate") or primary_stream.get("bit_rate")
    bit_rate_kbps = None
    if bit_rate:
        try:
            bit_rate_kbps = int(round(int(bit_rate) / 1000))
        except (ValueError, TypeError):
            pass

    return {
        "duration_seconds": round(duration, 3),
        "formatted_duration": format_duration_hms(duration),
        "human_duration": format_duration_human(duration),
        "file_size_bytes": file_size,
        "formatted_size": format_file_size(file_size),
        "container_format": container_format,
        "codec_name": codec_name,
        "sample_rate": f"{sample_rate} Hz" if sample_rate != "unknown" else "Unknown",
        "channels": channels,
        "channel_layout": channel_layout,
        "bit_rate_kbps": f"{bit_rate_kbps} kbps" if bit_rate_kbps else "Variable",
        "audio_stream_count": len(audio_streams),
        "is_video_container": any(s.get("codec_type") == "video" for s in streams)
    }


def determine_output_profile(source_filename_or_ext: str, metadata: Dict[str, Any]) -> Tuple[str, List[str], str]:
    """
    Determines output extension, FFmpeg encoding arguments, and a human description.
    Prioritizes stream-copy for identical format preservation when safe.
    Extracts pure audio from MP4 files without video.
    Evaluates actual media metadata (codec, container, video stream)
    and handles filenames with multiple or unusual extensions (e.g. .MP3.mpeg).
    """
    codec = metadata.get("codec_name", "").lower()
    container = metadata.get("container_format", "").lower()
    is_video = metadata.get("is_video_container", False)

    # Extract all lowercase suffixes from the filename
    suffixes = [s.lower().lstrip(".") for s in Path(source_filename_or_ext).suffixes]
    if not suffixes and source_filename_or_ext:
        suffixes = [source_filename_or_ext.lower().lstrip(".")]

    # 1. MP4 Video input or video container: Extract pure audio track without video
    if is_video or any(s in ["mp4", "m4v"] for s in suffixes) or "mp4" in container:
        if codec == "aac":
            # Direct stream-copy AAC audio into M4A container (lossless, instant, no video)
            return "m4a", ["-vn", "-c:a", "copy"], "Extracted native AAC audio into M4A without re-encoding"
        elif codec == "mp3":
            return "mp3", ["-vn", "-c:a", "copy"], "Extracted native MP3 audio without re-encoding"
        else:
            # Transcode audio to high-quality MP3 (256kbps)
            return "mp3", ["-vn", "-c:a", "libmp3lame", "-b:a", "256k"], "Transcoded audio to 256k MP3"

    # 2. Native MP3 audio (or MPEG audio layer)
    if codec in ["mp3", "mp2"] or any(s in ["mp3", "mpeg", "mpg"] for s in suffixes):
        return "mp3", ["-c:a", "copy"], "Native MP3 stream copy (lossless)"

    # 3. Native WAV audio (PCM)
    if "pcm" in codec or codec == "wav" or "wav" in suffixes:
        return "wav", ["-c:a", "copy"], "PCM WAV stream copy (lossless)"

    # 4. Native FLAC audio
    if codec == "flac" or "flac" in suffixes:
        return "flac", ["-c:a", "copy"], "FLAC stream copy (lossless)"

    # 5. Native OGG audio (Vorbis / Opus)
    if codec in ["vorbis", "opus"] or any(s in ["ogg", "oga", "opus"] for s in suffixes):
        return "ogg", ["-c:a", "copy"], "OGG Vorbis/Opus stream copy (lossless)"

    # 6. Native M4A / AAC audio
    if codec == "aac" or any(s in ["m4a", "aac"] for s in suffixes):
        return "m4a", ["-c:a", "copy"], "AAC M4A stream copy (lossless)"

    # 7. Fallback for other formats: Transcode to high-quality MP3 (256k)
    return "mp3", ["-c:a", "libmp3lame", "-b:a", "256k"], "Transcoded to 256k MP3"


def execute_split_segment(
    input_file: Path,
    output_file: Path,
    start_sec: float,
    duration_sec: Optional[float],
    encode_args: List[str]
) -> bool:
    """
    Executes FFmpeg cut for a single segment using fast input seeking (-ss before -i).
    Uses argument list for secure subprocess execution.
    If stream-copy fails, automatically falls back to re-encoding.
    """
    # Fast input seeking (-ss before -i) allows instantaneous container indexing
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-ss", str(round(start_sec, 3)),
        "-i", str(input_file)
    ]

    if duration_sec is not None and duration_sec > 0:
        cmd.extend(["-t", str(round(duration_sec, 3))])

    cmd.extend(encode_args)
    cmd.append(str(output_file))

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=SEGMENT_TIMEOUT_SECONDS,
            check=False
        )
        if proc.returncode == 0 and output_file.exists() and output_file.stat().st_size > 0:
            return True
        else:
            logger.warning(f"Fast segment execution failed with args {encode_args}. Error: {proc.stderr}")
    except Exception as e:
        logger.warning(f"Exception during segment split: {e}")

    # Fallback: if stream-copy failed or produced invalid file, attempt high-quality re-encode with fast seek
    logger.info("Attempting segment fallback transcode...")
    fallback_output = output_file
    fallback_args = ["-vn", "-c:a", "libmp3lame", "-b:a", "192k"]
    if output_file.suffix.lower() in [".m4a", ".aac"]:
        fallback_args = ["-vn", "-c:a", "aac", "-b:a", "192k"]
    elif output_file.suffix.lower() == ".wav":
        fallback_args = ["-vn", "-c:a", "pcm_s16le"]

    fallback_cmd = [
        FFMPEG_BIN,
        "-y",
        "-ss", str(round(start_sec, 3)),
        "-i", str(input_file)
    ]
    if duration_sec is not None and duration_sec > 0:
        fallback_cmd.extend(["-t", str(round(duration_sec, 3))])
    fallback_cmd.extend(fallback_args)
    fallback_cmd.append(str(fallback_output))

    try:
        proc_fallback = subprocess.run(
            fallback_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=SEGMENT_TIMEOUT_SECONDS,
            check=False
        )
        return proc_fallback.returncode == 0 and fallback_output.exists() and fallback_output.stat().st_size > 0
    except Exception as e:
        logger.error(f"Fallback transcode failed: {e}")
        return False


def verify_audio_file(file_path: Path, expected_duration: Optional[float] = None) -> Tuple[bool, float, int]:
    """
    Verifies that an output segment is valid and non-empty.
    Uses fast filesystem inspection first; checks duration via ffprobe when needed.
    """
    if not file_path.exists():
        return False, 0.0, 0

    size = file_path.stat().st_size
    if size < 512:
        return False, 0.0, 0

    # If expected_duration is provided and valid, use it directly (saving a redundant ffprobe child process)
    if expected_duration is not None and expected_duration > 0:
        return True, round(expected_duration, 2), size

    cmd = [
        FFPROBE_BIN,
        "-v", "error",
        "-show_entries", "format=duration,size",
        "-of", "json",
        str(file_path)
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            check=False
        )
        if result.returncode != 0:
            return False, 0.0, 0
        data = json.loads(result.stdout)
        dur = float(data.get("format", {}).get("duration", 0.0))
        file_sz = int(data.get("format", {}).get("size", size))
        return dur > 0, dur, file_sz
    except Exception:
        return False, 0.0, 0


def create_zip_archive(files: List[Path], zip_destination: Path) -> int:
    """
    Creates a fast ZIP archive of generated audio segments.
    Uses ZIP_STORED because audio files (MP3, M4A, FLAC, OGG) are already compressed media.
    Avoids wasting CPU re-compressing uncompressible data, reducing archive creation time by ~10x.
    """
    zip_destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_destination, "w", compression=zipfile.ZIP_STORED) as zf:
        for f in files:
            zf.write(f, arcname=f.name)

    return zip_destination.stat().st_size
