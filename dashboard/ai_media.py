import json
import mimetypes
import os
import tempfile
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path

from system_admin import save_uploaded_stream
from utils import command_exists, run_capture


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}



def _seconds_to_timestamp(value):
    value = max(0.0, float(value or 0.0))
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    seconds = value % 60
    millis = int(round((seconds - int(seconds)) * 1000))
    whole_seconds = int(seconds)
    if millis >= 1000:
        whole_seconds += 1
        millis = 0
    return hours, minutes, whole_seconds, millis


def format_srt_time(value):
    h, m, s, ms = _seconds_to_timestamp(value)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_vtt_time(value):
    h, m, s, ms = _seconds_to_timestamp(value)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def build_srt_from_segments(segments):
    blocks = []
    for idx, seg in enumerate(segments or [], start=1):
        text = str((seg or {}).get("text") or "").strip()
        if not text:
            continue
        start = format_srt_time(seg.get("start"))
        end = format_srt_time(seg.get("end"))
        blocks.append(f"{idx}\n{start} --> {end}\n{text}")
    return "\n\n".join(blocks).strip()


def build_vtt_from_segments(segments):
    body = []
    for seg in segments or []:
        text = str((seg or {}).get("text") or "").strip()
        if not text:
            continue
        start = format_vtt_time(seg.get("start"))
        end = format_vtt_time(seg.get("end"))
        body.append(f"{start} --> {end}\n{text}")
    content = "\n\n".join(body).strip()
    return "WEBVTT\n\n" + content if content else "WEBVTT\n"


def _extract_audio_from_video(source_path):
    if not command_exists("ffmpeg"):
        return False, "ffmpeg is required for video subtitle processing.", ""
    audio_fd, audio_path = tempfile.mkstemp(prefix="serverinstaller-audio-", suffix=".wav")
    os.close(audio_fd)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        audio_path,
    ]
    rc, out = run_capture(cmd, timeout=1800)
    if rc != 0:
        try:
            Path(audio_path).unlink(missing_ok=True)
        except Exception:
            pass
        return False, out or "ffmpeg audio extraction failed.", ""
    return True, "", audio_path


def _burn_subtitles_into_video(video_path, subtitle_path):
    if not command_exists("ffmpeg"):
        return False, "ffmpeg is required for burnt-in subtitles.", ""
    out_path = str(Path(video_path).with_name(Path(video_path).stem + "-subtitled.mp4"))
    filter_path = str(subtitle_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"subtitles='{filter_path}'",
        "-c:a",
        "copy",
        out_path,
    ]
    rc, out = run_capture(cmd, timeout=3600)
    if rc != 0:
        return False, out or "ffmpeg subtitle burn failed.", ""
    return True, "", out_path


def _post_whisper_file(url, field_name, file_path, filename, response_format="verbose_json", language="", task="transcribe"):
    boundary = "----ServerInstallerBoundary"
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    parts = []
    def add_field(name, value):
        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        parts.append(str(value).encode("utf-8"))
        parts.append(b"\r\n")
    parts.append(f"--{boundary}\r\n".encode("utf-8"))
    parts.append(f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode("utf-8"))
    parts.append(f"Content-Type: {mime}\r\n\r\n".encode("utf-8"))
    parts.append(file_bytes)
    parts.append(b"\r\n")
    add_field("response_format", response_format)
    add_field("task", task)
    if language:
        add_field("language", language)
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=3600) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def transcribe_media_with_whisper(whisper_base_url, upload_part, subtitle_format="srt", language="", task="transcribe", burn_subtitles=False):
    if not whisper_base_url:
        return False, "Whisper is not installed or no service URL is available.", {}

    saved_path = save_uploaded_stream(upload_part.get("filename") or "media.bin", BytesIO(upload_part.get("content") or b""))
    media_path = Path(saved_path)
    work_audio = str(media_path)
    cleanup_paths = []
    is_video = media_path.suffix.lower() in VIDEO_EXTENSIONS or (upload_part.get("content_type") or "").lower().startswith("video/")
    if is_video:
        ok, err, extracted_audio = _extract_audio_from_video(media_path)
        if not ok:
            return False, err, {}
        work_audio = extracted_audio
        cleanup_paths.append(extracted_audio)

    endpoints = [
        (whisper_base_url.rstrip("/") + "/v1/audio/transcriptions", "file"),
        (whisper_base_url.rstrip("/") + "/transcribe", "audio"),
    ]
    payload = None
    errors = []
    for endpoint, field_name in endpoints:
        try:
            payload = _post_whisper_file(endpoint, field_name, work_audio, media_path.name, response_format="verbose_json", language=language, task=task)
            break
        except urllib.error.HTTPError as ex:
            body = ex.read().decode("utf-8", errors="replace")
            errors.append(f"{endpoint}: HTTP {ex.code} {body}".strip())
        except Exception as ex:
            errors.append(f"{endpoint}: {ex}")
    for path in cleanup_paths:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            pass
    if payload is None:
        return False, " | ".join(errors) if errors else "Whisper transcription request failed.", {}

    text = str(payload.get("text") or payload.get("result") or "").strip()
    segments = payload.get("segments") or []
    if not segments and text:
        segments = [{"start": 0, "end": max(1, len(text.split()) * 0.45), "text": text}]
    srt = build_srt_from_segments(segments)
    vtt = build_vtt_from_segments(segments)
    chosen_format = str(subtitle_format or "srt").strip().lower()
    subtitle_text = text if chosen_format == "txt" else (vtt if chosen_format == "vtt" else srt)

    subtitle_ext = {"txt": ".txt", "vtt": ".vtt"}.get(chosen_format, ".srt")
    subtitle_path = str(media_path.with_suffix(subtitle_ext))
    Path(subtitle_path).write_text(subtitle_text, encoding="utf-8")

    burned_video_path = ""
    burn_error = ""
    if burn_subtitles and is_video:
        ok, burn_error, burned_video_path = _burn_subtitles_into_video(str(media_path), subtitle_path)

    result = {
        "text": text,
        "segments": segments,
        "subtitle_format": chosen_format,
        "subtitle_text": subtitle_text,
        "subtitle_path": subtitle_path,
        "source_path": str(media_path),
        "is_video": is_video,
        "burned_video_path": burned_video_path,
        "burn_error": burn_error,
    }
    return True, "", result
