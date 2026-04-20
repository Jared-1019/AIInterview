#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Installing backend Python dependencies..."
python3 -m pip install -r requirements.txt -i https://pypi.org/simple

cd "$SCRIPT_DIR/server"

echo "Starting LLM server on http://127.0.0.1:3000"
python3 llm_server.py > /tmp/ai_interview_llm.log 2>&1 &
LLM_PID=$!

echo "Starting ASR server on http://127.0.0.1:3001"
python3 asr_server.py > /tmp/ai_interview_asr.log 2>&1 &
ASR_PID=$!

echo "Starting TTS server on http://127.0.0.1:3002"
python3 tts_server.py > /tmp/ai_interview_tts.log 2>&1 &
TTS_PID=$!

echo "Starting Phone server on http://127.0.0.1:3003"
python3 phone_server.py > /tmp/ai_interview_phone.log 2>&1 &
PHONE_PID=$!

trap 'echo "Stopping backend..."; kill $LLM_PID $ASR_PID $TTS_PID $PHONE_PID 2>/dev/null || true; exit' INT TERM EXIT

echo "Backend started successfully."
echo "  LLM: http://127.0.0.1:3000"
echo "  ASR: http://127.0.0.1:3001"
echo "  TTS: http://127.0.0.1:3002"
echo "  Phone: http://127.0.0.1:3003"
echo "Logs: /tmp/ai_interview_llm.log /tmp/ai_interview_asr.log /tmp/ai_interview_tts.log /tmp/ai_interview_phone.log"

echo "Press Ctrl+C to stop."
wait
