import base64
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from capture import Shot, record
from narration import SCRIPT, narrate

HERE = Path(__file__).resolve().parent
FPS = 30
WIDTH, HEIGHT = 1080, 1350
NAME = "regularag-linkedin"


def find_tool(name: str) -> str:
    bundled = next((HERE / ".venv" / "ffmpeg").glob(f"*/bin/{name}.exe"), None)
    path = bundled or shutil.which(name)
    if not path:
        raise RuntimeError(f"Install {name} and put it on PATH before building")
    return str(path)


def make_player(output: Path, mp4: Path) -> None:
    video = base64.b64encode(mp4.read_bytes()).decode("ascii")
    output.write_text(
        f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RegulaRAG Indonesia · A citation walkthrough</title>
<style>
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: #060e1a; color-scheme: dark; }}
  video {{ display: block; width: min(100%, 680px); max-height: 100vh; max-height: 100dvh; aspect-ratio: 4 / 5; }}
</style>
<video controls playsinline preload="metadata" aria-label="RegulaRAG Indonesia video">
  <source type="video/mp4" src="data:video/mp4;base64,{video}">
  Open the MP4 file in a video player.
</video>
</html>
""",
        encoding="utf-8",
    )


def edit(work: Path, shots: list[Shot], scenes: list[dict], frame_count: int) -> str:
    starts = [
        round((scenes[shot.scene]["cues"][shot.cue]["from"] - 0.10) * FPS)
        for shot in shots
    ]
    starts[0] = 0
    lengths = [end - start for start, end in zip(starts, starts[1:] + [frame_count])]
    if not all(length > 0 for length in lengths):
        raise ValueError("Shots must follow the narration in chronological order")

    parts = []
    for index, (shot, length) in enumerate(zip(shots, lengths)):
        ratio = min(1.15, length / FPS / (shot.end - shot.start))
        parts.append(
            f"[source{index}]trim=start={shot.start:.3f}:end={shot.end:.3f},"
            f"setpts=(PTS-STARTPTS)*{ratio:.5f},fps={FPS},"
            f"tpad=stop_mode=clone:stop={length},trim=end_frame={length}[shot{index}]"
        )
    inputs = "".join(f"[source{i}]" for i in range(len(shots)))
    cuts = "".join(f"[shot{i}]" for i in range(len(shots)))
    (work / "captions.ass").write_text(captions(scenes), encoding="utf-8")
    return ";".join(
        [
            f"[0:v]split={len(shots)}{inputs}",
            *parts,
            (
                f"{cuts}concat=n={len(shots)}:v=1:a=0,"
                f"scale={WIDTH}:1125:flags=lanczos,setsar=1,"
                f"pad={WIDTH}:{HEIGHT}:0:0:color=0x102137,subtitles=captions.ass[video]"
            ),
        ]
    )


def captions(scenes: list[dict]) -> str:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1350
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,46,&H00FFFFFF,&H00FFFFFF,&H00102037,&H00102037,-1,0,0,0,100,100,0,0,1,0,0,2,70,70,67,1
Style: Translation,Arial,35,&H00D3F58D,&H00FFFFFF,&H00102037,&H00102037,-1,0,0,0,100,100,0,0,1,0,0,2,70,70,166,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def timestamp(seconds):
        minutes, hundredths = divmod(round(seconds * 100), 6000)
        return f"0:{minutes:02}:{hundredths // 100:02}.{hundredths % 100:02}"

    lines = []
    for scene in scenes:
        for cue in scene["cues"]:
            text = cue["text"].replace("\n", r"\N")
            start, end = timestamp(cue["from"]), timestamp(cue["to"])
            lines.append(f"Dialogue: 0,{start},{end},Caption,,0,0,0,,{text}")
            if "three times twenty-four" in text:
                lines.append(
                    f"Dialogue: 0,{start},{end},Translation,,0,0,0,,Unofficial English translation"
                )
    return header + "\n".join(lines) + "\n"


def verify_mp4(ffprobe: str, mp4: Path, frame_count: int) -> dict:
    result = subprocess.check_output(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", mp4]
    )
    metadata = json.loads(result)
    video, audio = metadata["streams"]
    if (
        (
            video["codec_name"],
            video["pix_fmt"],
            video["width"],
            video["height"],
            video["avg_frame_rate"],
        )
        != ("h264", "yuv420p", WIDTH, HEIGHT, f"{FPS}/1")
        or int(video["nb_frames"]) != frame_count
        or (audio["codec_name"], audio["sample_rate"], audio["tags"]["language"])
        != ("aac", "48000", "eng")
        or abs(float(video["duration"]) - float(audio["duration"])) > 0.1
        or not 192_000
        <= int(video["bit_rate"])
        <= int(metadata["format"]["bit_rate"])
        <= 30_000_000
    ):
        raise RuntimeError("MP4 failed the video, audio or synchronization checks")
    return metadata


def main() -> None:
    ffmpeg, ffprobe = find_tool("ffmpeg"), find_tool("ffprobe")
    scratch = (HERE / ".venv").resolve()
    if scratch.parent != HERE:
        raise RuntimeError(
            "The video virtual environment must be inside the video folder"
        )
    with tempfile.TemporaryDirectory(prefix="render-", dir=scratch) as temporary:
        work = Path(temporary)
        footage, shots, dense_status = record(work, ffmpeg)
        script = SCRIPT
        if dense_status == "error":
            dense_error = (
                *SCRIPT[4][:-1],
                ("The app reports an error.\nDense search stops here.", 0.32),
            )
            script = (*SCRIPT[:4], dense_error, SCRIPT[5])
        narration = work / "narration.wav"
        scenes, duration = narrate(narration, script)
        if not 70 <= duration <= 85:
            raise RuntimeError(
                f"Narration runs {duration:.2f}s. The storyboard calls for 70–85 seconds."
            )
        audio = work / "narration.m4a"
        subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-i",
                narration,
                "-af",
                f"loudnorm=I=-16:LRA=7:TP=-1.5,atrim=duration={duration:.6f}",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                audio,
            ],
            check=True,
        )
        html, mp4 = work / f"{NAME}.html", work / f"{NAME}.mp4"
        frame_count = math.ceil(duration * FPS)
        filters = edit(work, shots, scenes, frame_count)
        subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-i",
                footage,
                "-i",
                audio,
                "-filter_complex_threads",
                "2",
                "-filter_complex",
                filters,
                "-map",
                "[video]",
                "-map",
                "1:a:0",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-b:v",
                "900k",
                "-minrate",
                "900k",
                "-maxrate",
                "900k",
                "-bufsize",
                "1800k",
                "-x264-params",
                "filler=1",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "copy",
                "-metadata:s:a:0",
                "language=eng",
                "-movflags",
                "+faststart",
                mp4,
            ],
            cwd=work,
            check=True,
        )
        metadata = verify_mp4(ffprobe, mp4, frame_count)
        make_player(html, mp4)
        html.replace(HERE / html.name)
        mp4.replace(HERE / mp4.name)
        print(
            f"Built both files. MP4 runtime {float(metadata['format']['duration']):.3f}s, {frame_count:,} frames."
        )


if __name__ == "__main__":
    main()
