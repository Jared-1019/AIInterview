# Please install required packages first: `pip3 install flask openai`
import os
from pathlib import Path
from flask import Flask, Response, jsonify, request, send_from_directory
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / 'frontend'

api_key = "sk-12af5cfed59843c4bd4bc8590070f111"

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com")

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path='')

@app.route('/')
def index():
    return send_from_directory(str(FRONTEND_DIR), 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(str(FRONTEND_DIR), path)

@app.route('/api/chat', methods=['POST'])
def chat():
    payload = request.get_json(force=True)
    user_message = payload.get('message', '').strip()
    if not user_message:
        return jsonify({'error': 'Empty message'}), 400

    response_stream = client.chat.completions.create(
        model='deepseek-chat',
        messages=[
            {'role': 'system', 'content': 'You are a helpful assistant.'},
            {'role': 'user', 'content': user_message},
        ],
        stream=True,
    )

    def generate():
        for chunk in response_stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = getattr(choice.delta, 'content', None)
            if delta:
                yield delta

    return Response(generate(), mimetype='text/plain')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)