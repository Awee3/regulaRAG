from pathlib import Path

import numpy as np
import soundfile as sf
from supertonic import TTS

HERE = Path(__file__).resolve().parent
VOICE = "M4"

# Each entry holds the caption, its line break, and the pause after the clip.
SCRIPT = (
    (
        ("This is RegulaRAG.", 0.22),
        (
            "It searches official Indonesian data\nprotection documents on a local computer.",
            0.24,
        ),
        ("Let’s follow one question\nto its source.", 0.42),
    ),
    (
        (
            "What’s the deadline for notifying someone\nafter a personal data breach?",
            0.24,
        ),
        ("I’ll enter that question and leave\nthe document filter open", 0.10),
        ("so we can search the collection.", 0.30),
    ),
    (
        ("The search menu offers four methods.", 0.58),
        ("I’ll start with BM25, which looks\nfor matching words,", 0.15),
        ("then submit the question.", 0.32),
    ),
    (
        ("The local Qwen model\nselected this passage.", 0.22),
        ("It gives the deadline as\nthree times twenty-four hours.", 0.34),
        ("Opening the citation\nshows Article forty-six.", 0.40),
        ("That’s page nineteen of the PDF,\nwith a link to the official source.", 0.36),
    ),
    (
        ("I’ll keep the question and\nswitch to dense search.", 0.20),
        ("This option uses E5 to find\npassages with similar meaning.", 0.23),
        ("Submitting again runs that search.", 0.26),
        ("Both methods pass their results\nto the same answer model.", 0.32),
    ),
    (
        ("What if I ask about flights\nfrom Jakarta to Tokyo?", 0.26),
        ("The app reports that it has\ntoo little evidence", 0.13),
        ("and returns no citations.", 0.20),
        ("Its collection covers\ndata protection documents.", 2.90),
    ),
)


def narrate(output: Path, script=SCRIPT) -> tuple[list[dict], float]:
    tts = TTS(model="supertonic-3", model_dir=HERE / ".venv" / "supertonic-3")
    voice = tts.get_voice_style(VOICE)
    np.random.seed(20261123)
    rate = tts.sample_rate
    audio = [np.zeros(round(0.28 * rate), dtype=np.float32)]
    cursor = len(audio[0])
    scenes = []
    for scene_number, lines in enumerate(script):
        lead = 0.17 if scene_number else cursor / rate
        start = cursor / rate - lead
        cues = []
        for caption, pause in lines:
            spoken = (
                caption.replace("\n", " ")
                .replace("RegulaRAG", "Regula Rag")
                .replace("Qwen", "Kwen")
                .replace("BM25", "B M twenty-five")
                .replace("E5", "E five")
            )
            clip, _ = tts.synthesize(
                spoken, voice, lang="en", total_steps=10, speed=0.83
            )
            clip = clip.ravel()
            active = np.flatnonzero(np.abs(clip) > np.max(np.abs(clip)) * 0.025)
            if not active.size:
                raise ValueError(f"Silent narration clip for {caption!r}")
            clip = clip[
                max(0, active[0] - round(0.035 * rate)) : active[-1]
                + round(0.090 * rate)
            ]
            fade = np.linspace(0, 1, round(0.010 * rate))
            clip[: len(fade)] *= fade
            clip[-len(fade) :] *= fade[::-1]
            end = cursor + len(clip)
            cues.append({"from": cursor / rate, "to": end / rate, "text": caption})
            audio.extend((clip, np.zeros(round(pause * rate), dtype=np.float32)))
            cursor = end + len(audio[-1])
        scenes.append({"start": start, "cues": cues})
        print(
            f"Scene {scene_number + 1} from {start:.2f}s to {cursor / rate:.2f}s",
            flush=True,
        )

    waveform = np.concatenate(audio)
    waveform *= min(1, 0.95 / np.max(np.abs(waveform)))
    sf.write(output, waveform, rate, subtype="PCM_16")
    return scenes, len(waveform) / rate
