import base64
import io

import requests
from flask import Flask, jsonify, request
from tts_server import synthesize_wav
from asr_server import convert_to_wav_stream, transcribe_wav

app = Flask(__name__)


@app.after_request
def add_cors(response):
    origin = request.headers.get('Origin')
    response.headers['Access-Control-Allow-Origin'] = origin or '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response


LLM_URL = 'http://127.0.0.1:3000/api/chat'
ASR_STATUS_URL = 'http://127.0.0.1:3001/api/asr/status'
TTS_STATUS_URL = 'http://127.0.0.1:3002/api/tts/status'
LLM_ROOT_URL = 'http://127.0.0.1:3000/'


def ask_llm(text: str) -> str:
    response = requests.post(LLM_URL, json={'message': text}, stream=True, timeout=120)
    response.raise_for_status()

    result_text = ''
    for chunk in response.iter_content(chunk_size=4096):
        if not chunk:
            continue
        result_text += chunk.decode('utf-8', errors='ignore')

    return result_text.strip()


def service_status(url: str, method: str = 'GET') -> dict:
    try:
        response = requests.request(method, url, timeout=5)
        return {'ok': response.ok, 'status_code': response.status_code}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}


@app.route('/api/phone', methods=['POST'])
def phone():
    silent_request = request.form.get('silent') == 'true'
    recognized_text = ''

    if not silent_request:
        if 'audio' not in request.files:
            return jsonify({'error': 'Missing audio file for voice request.'}), 400

        audio_file = request.files['audio']
        if not audio_file or not audio_file.filename:
            return jsonify({'error': 'Invalid audio file.'}), 400

        try:
            file_bytes = audio_file.read()
            wav_stream = convert_to_wav_stream(file_bytes)
            recognized_text = transcribe_wav(wav_stream)
        except Exception as exc:
            return jsonify({'error': f'ASR failed: {exc}'}), 400

    if not recognized_text:
        recognized_text = '用户没有说话'

    try:
        assistant_text = ask_llm(recognized_text)
    except Exception as exc:
        return jsonify({'error': f'LLM request failed: {exc}'}), 500

    print('=== phone call conversation ===')
    print(f'input_text: {recognized_text}')
    print(f'llm response: {assistant_text}')
    print('==============================')

    try:
        wav_buffer = synthesize_wav(assistant_text)
        wav_bytes = wav_buffer.read()
        audio_base64 = base64.b64encode(wav_bytes).decode('utf-8')
    except Exception as exc:
        return jsonify({'error': f'TTS failed: {exc}'}), 500

    return jsonify({
        'input_text': recognized_text,
        'response_text': assistant_text,
        'audio_base64': audio_base64,
    })


@app.route('/api/phone/status', methods=['GET'])
def status():
    status_report = {
        'phone': 'ready',
        'llm': service_status(LLM_ROOT_URL),
        'asr': service_status(ASR_STATUS_URL),
        'tts': service_status(TTS_STATUS_URL),
    }
    return jsonify(status_report)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3003, debug=True)
