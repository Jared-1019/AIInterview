import io
import subprocess
from pathlib import Path

from flask import Flask, jsonify, request, send_file
from gtts import gTTS

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
SAMPLE_RATE = 24000


def synthesize_wav(text: str) -> io.BytesIO:
    if not text:
        raise ValueError('Text is required')

    mp3_buffer = io.BytesIO()
    gTTS(text=text, lang='zh-cn').write_to_fp(mp3_buffer)
    mp3_buffer.seek(0)

    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as mp3_file:
        mp3_file.write(mp3_buffer.read())
        mp3_path = mp3_file.name

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_file:
        wav_path = wav_file.name

    try:
        ffmpeg_cmd = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'error',
            '-y',
            '-i', mp3_path,
            '-ac', '1',
            '-ar', str(SAMPLE_RATE),
            wav_path,
        ]

        process = subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if process.returncode != 0:
            raise RuntimeError(
                f'ffmpeg conversion failed: {process.stderr.decode(errors="ignore").strip()}'
            )

        with open(wav_path, 'rb') as f:
            wav_data = f.read()

        return io.BytesIO(wav_data)
    finally:
        import os
        try:
            os.remove(mp3_path)
        except OSError:
            pass
        try:
            os.remove(wav_path)
        except OSError:
            pass


@app.route('/api/tts', methods=['POST'])
def tts():
    payload = request.get_json(force=True)
    text = payload.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Text is required'}), 400

    try:
        wav_buffer = synthesize_wav(text)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

    return send_file(
        wav_buffer,
        mimetype='audio/wav',
        as_attachment=True,
        download_name='tts.wav',
    )


@app.route('/api/tts/status', methods=['GET'])
def status():
    return jsonify({
        'status': 'ok',
        'model': 'gTTS_zh',
        'sample_rate': SAMPLE_RATE,
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3002, debug=True)
