import io
import json
import subprocess
import wave
from pathlib import Path

from flask import Flask, jsonify, request
from vosk import KaldiRecognizer, Model

BASE_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = BASE_DIR / "model"

if not MODEL_DIR.exists():
    raise RuntimeError(
        "Vosk model not found. Please download a lightweight Chinese model and unpack it into backend/model. "
        "Example: vosk-model-small-cn-0.22"
    )

model = Model(str(MODEL_DIR))
app = Flask(__name__)


@app.after_request
def add_cors(response):
    origin = request.headers.get("Origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    else:
        response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def convert_to_wav_stream(payload_bytes):
    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        "pipe:0",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        "pipe:1",
    ]

    process = subprocess.run(
        ffmpeg_cmd,
        input=payload_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if process.returncode != 0:
        raise RuntimeError(
            f"ffmpeg conversion failed: {process.stderr.decode(errors='ignore').strip()}"
        )

    return io.BytesIO(process.stdout)


def transcribe_wav(stream):
    with wave.open(stream, "rb") as wf:
        if wf.getnchannels() != 1:
            raise ValueError("Audio must be mono WAV (1 channel).")
        if wf.getsampwidth() != 2:
            raise ValueError("Audio must be 16-bit PCM WAV.")

        recognizer = KaldiRecognizer(model, wf.getframerate())
        recognizer.SetWords(True)

        text_segments = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text_segments.append(result.get("text", ""))

        final_result = json.loads(recognizer.FinalResult())
        text_segments.append(final_result.get("text", ""))

        return " ".join(segment for segment in text_segments if segment).strip()


@app.route("/api/asr", methods=["POST", "OPTIONS"])
def asr():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    if "audio" not in request.files:
        return jsonify({"error": "Missing form field 'audio'. Specify a WAV file."}), 400

    audio_file = request.files["audio"]
    if audio_file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    try:
        file_bytes = audio_file.read()
        wav_stream = convert_to_wav_stream(file_bytes)
        transcript = transcribe_wav(wav_stream)
    except Exception as err:
        return jsonify({"error": str(err)}), 400

    return jsonify({"text": transcript})


@app.route("/api/asr/status", methods=["GET"])
def status():
    return jsonify({"status": "ok", "model_path": str(MODEL_DIR)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3001, debug=True)
