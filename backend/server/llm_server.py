# Please install required packages first: `pip3 install flask openai`
import os
from pathlib import Path
from flask import Flask, Response, jsonify, request, send_from_directory
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / 'frontend'

api_key = "sk-12af5cfed59843c4bd4bc8590070f111"

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com")

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path='')

@app.route('/')
def index():
    return send_from_directory(str(FRONTEND_DIR), 'index.html')

@app.route('/images/<path:filename>')
def image_files(filename):
    return send_from_directory(str(BASE_DIR / 'images'), filename)

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

@app.route('/api/interview-chat', methods=['POST'])
def interview_chat():
    payload = request.get_json(force=True)
    user_message = payload.get('message', '').strip()
    position = payload.get('position', '').strip()
    is_first_message = payload.get('isFirstMessage', False)
    
    if not user_message:
        return jsonify({'error': 'Empty message'}), 400

    if is_first_message:
        # 第一次消息，使用前端传来的提示词作为面试官的开场白
        system_prompt = f"""你是一个专业的{position}岗位面试官，正在进行一场模拟面试。

面试规则：
1. 保持专业、礼貌的态度
2. 根据用户的回答进行针对性的追问
3. 对用户的回答给予适当的评价和反馈
4. 控制面试节奏，确保面试流程顺畅
5. 关注用户的技术能力、问题解决能力和沟通能力
6. 面试结束时给予综合评价和建议
7. 从自我介绍开始引导面试者，控制在3次问答内过渡到技术题目

请根据以上规则进行面试对话。"""
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message}
        ]
    else:
        # 后续消息，使用标准的面试官系统提示词
        system_prompt = f"""你是一个专业的{position}岗位面试官，正在进行一场模拟面试。

面试规则：
1. 保持专业、礼貌的态度
2. 根据用户的回答进行针对性的追问
3. 对用户的回答给予适当的评价和反馈
4. 控制面试节奏，确保面试流程顺畅
5. 关注用户的技术能力、问题解决能力和沟通能力
6. 面试结束时给予综合评价和建议
7. 从自我介绍开始引导面试者，控制在3次问答内过渡到技术题目

请根据以上规则进行面试对话。"""
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message}
        ]

    response_stream = client.chat.completions.create(
        model='deepseek-chat',
        messages=messages,
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

@app.route('/api/generate-questions', methods=['POST'])
def generate_questions():
    payload = request.get_json(force=True)
    position = payload.get('position', '').strip()
    custom_prompt = payload.get('prompt', '').strip()
    
    if not position:
        return jsonify({'error': 'Empty position'}), 400

    # 使用前端传来的提示词，如果没有则使用默认提示词
    default_prompt = f"""请为{position}岗位生成10道面试题目，难度递增。

要求：
1. 题目涵盖该岗位的核心技能和知识点
2. 题目难度从简单到困难递增
3. 每道题目需要标明难度等级（简单、中等、困难）
4. 题目要具体、有针对性
5. 输出格式为JSON数组，包含10个对象，每个对象包含id、difficulty、question三个字段

示例输出格式：
[
  {{
    "id": 1,
    "difficulty": "简单",
    "question": "请解释什么是RESTful API"
  }},
  ...
]
"""
    prompt = custom_prompt if custom_prompt else default_prompt

    response = client.chat.completions.create(
        model='deepseek-chat',
        messages=[
            {'role': 'system', 'content': 'You are an experienced interviewer. Generate interview questions based on the given position.'},
            {'role': 'user', 'content': prompt},
        ],
        response_format={"type": "json_object"}
    )

    return jsonify(response.choices[0].message.content)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)