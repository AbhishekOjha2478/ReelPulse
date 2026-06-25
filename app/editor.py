"""Heuristic auto-trim + Short/compilation builders.

Uses the system `ffmpeg` binary directly via subprocess (more predictable
than fighting a Python binding's kwarg semantics) and PySceneDetect for
finding scene-cut-dense "highlight" windows.

Every output gets the original audio muted by default (see
config.BACKGROUND_MUSIC_PATH) and a burned-in attribution overlay, since
that's both the CC BY attribution requirement and the "added value" that
distinguishes this from a plain re-upload.
"""

import logging
import subprocess
from pathlib import Path

from scenedetect import ContentDetector, detect

from app.config import (
    BACKGROUND_MUSIC_PATH,
    CHANNEL_BRAND_NAME,
    CLIP_SECONDS_PER_SOURCE,
    SHORT_MAX_SECONDS,
    TEMP_DIR,
)

logger = logging.getLogger(__name__)


def _run_ffmpeg(args):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd)}\n{result.stderr}")


def _probe_duration(video_path: str) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def _escape_drawtext(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", r"\'")


def pick_highlight_window(video_path: str, target_length: int) -> tuple:
    """Return (start, end) seconds for the scene-cut-densest window of target_length."""
    duration = _probe_duration(video_path)
    target_length = min(target_length, duration)

    try:
        scene_list = detect(video_path, ContentDetector())
        boundaries = sorted({s.get_seconds() for s, _ in scene_list} | {e.get_seconds() for _, e in scene_list})
    except Exception as exc:
        logger.warning("Scene detection failed for %s (%s); using a default window.", video_path, exc)
        boundaries = []

    if len(boundaries) < 2:
        start = duration * 0.2  # skip likely intro
        start = min(start, max(duration - target_length, 0))
        return start, start + target_length

    best_start, best_count = 0.0, -1
    for b in boundaries:
        if b + target_length > duration:
            continue
        count = sum(1 for x in boundaries if b <= x <= b + target_length)
        if count > best_count:
            best_start, best_count = b, count

    best_start = min(best_start, max(duration - target_length, 0))
    return best_start, best_start + target_length


def trim_clip(source_path: str, start: float, end: float, output_path: str):
    """Trim to [start, end) and attach either the configured background music
    or silence -- every output always carries an audio stream (even if silent)
    so later concatenation has consistent streams across segments."""
    duration = end - start
    if BACKGROUND_MUSIC_PATH:
        audio_input = ["-i", BACKGROUND_MUSIC_PATH]
    else:
        audio_input = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    args = [
        "-ss", str(start), "-i", source_path,
        *audio_input,
        "-t", str(duration),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
        output_path,
    ]
    _run_ffmpeg(args)


def _attribution_text(candidate) -> str:
    return f"Source: {candidate.title} by {candidate.channel_title} (CC BY) - link in description"


def build_short(candidate, source_path: str) -> str:
    """Vertical, captioned, attributed Short from one CC source video."""
    work_dir = Path(source_path).parent
    start, end = pick_highlight_window(source_path, SHORT_MAX_SECONDS)

    trimmed = str(work_dir / "trimmed.mp4")
    trim_clip(source_path, start, end, trimmed)

    vertical = str(work_dir / "vertical.mp4")
    _run_ffmpeg([
        "-i", trimmed,
        "-vf", "crop=ih*9/16:ih,scale=1080:1920",
        "-c:a", "copy",
        vertical,
    ])

    final_path = str(work_dir / "short_final.mp4")
    text = _escape_drawtext(_attribution_text(candidate))
    _run_ffmpeg([
        "-i", vertical,
        "-vf",
        f"drawtext=text='{text}':fontcolor=white:fontsize=28:x=(w-text_w)/2:y=h-th-60:"
        f"box=1:boxcolor=black@0.5:boxborderw=10",
        "-c:a", "copy",
        final_path,
    ])
    logger.info("Built short for %s -> %s", candidate.video_id, final_path)
    return final_path


def _build_attribution_card(text: str, output_path: str, seconds: int = 3):
    # Includes a silent audio track (not -an) so this segment has the same
    # stream layout as the real clips -- required for the concat step below.
    escaped = _escape_drawtext(text)
    _run_ffmpeg([
        "-f", "lavfi", "-i", f"color=c=black:s=1920x1080:d={seconds}",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-vf",
        f"drawtext=text='{escaped}':fontcolor=white:fontsize=40:x=(w-text_w)/2:y=(h-text_h)/2",
        "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-t", str(seconds),
        output_path,
    ])


def build_compilation(candidates_with_paths) -> str:
    """Concatenate several CC clips into one ~5 min video with intro/outro/attribution cards."""
    run_dir = TEMP_DIR / "compilation"
    run_dir.mkdir(parents=True, exist_ok=True)
    segment_paths = []

    intro_path = str(run_dir / "intro.mp4")
    _build_attribution_card(f"{CHANNEL_BRAND_NAME} presents", intro_path)
    segment_paths.append(intro_path)

    for idx, (candidate, source_path) in enumerate(candidates_with_paths):
        work_dir = Path(source_path).parent
        start, end = pick_highlight_window(source_path, CLIP_SECONDS_PER_SOURCE)

        trimmed = str(work_dir / f"trimmed_{idx}.mp4")
        trim_clip(source_path, start, end, trimmed)

        scaled = str(work_dir / f"scaled_{idx}.mp4")
        _run_ffmpeg(["-i", trimmed, "-vf", "scale=1920:1080", "-c:a", "copy", scaled])

        card_path = str(work_dir / f"card_{idx}.mp4")
        _build_attribution_card(_attribution_text(candidate), card_path)

        segment_paths.append(card_path)
        segment_paths.append(scaled)

    outro_path = str(run_dir / "outro.mp4")
    _build_attribution_card(f"Thanks for watching {CHANNEL_BRAND_NAME}", outro_path)
    segment_paths.append(outro_path)

    # Re-encode every segment to a uniform codec/resolution/audio layout so the
    # concat demuxer (which requires matching streams) works reliably.
    normalized_paths = []
    for i, path in enumerate(segment_paths):
        normalized = str(run_dir / f"norm_{i}.mp4")
        _run_ffmpeg([
            "-i", path,
            "-vf", "scale=1920:1080,fps=30",
            "-c:v", "libx264", "-preset", "veryfast",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            normalized,
        ])
        normalized_paths.append(normalized)

    list_file = run_dir / "concat_list.txt"
    list_file.write_text("\n".join(f"file '{p}'" for p in normalized_paths), encoding="utf-8")

    final_path = str(run_dir / "compilation_final.mp4")
    _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", final_path])

    logger.info("Built compilation with %d clips -> %s", len(candidates_with_paths), final_path)
    return final_path
