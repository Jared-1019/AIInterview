# Please install required packages first: `pip3 install flask openai`
import json
import os
import requests
from pathlib import Path
from flask import Flask, Response, jsonify, request, send_from_directory
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / 'frontend'
PROMPTS_DIR = BASE_DIR / 'prompts'

# 加载提示词文件
def load_prompts():
    prompts = {}
    try:
        # 加载面试流程提示词
        with open(PROMPTS_DIR / 'interview_flow.json', 'r', encoding='utf-8') as f:
            prompts['interview_flow'] = json.load(f)
        
        # 加载题目生成提示词
        with open(PROMPTS_DIR / 'question_generation.json', 'r', encoding='utf-8') as f:
            prompts['question_generation'] = json.load(f)
        
        # 加载面试官角色提示词
        with open(PROMPTS_DIR / 'interviewer_role.json', 'r', encoding='utf-8') as f:
            prompts['interviewer_role'] = json.load(f)
    except Exception as e:
        print(f"Error loading prompts: {e}")
    return prompts

# 全局提示词字典
PROMPTS = load_prompts()

# RAG 检索函数
def rag_retrieve(query, top_k=5):
    """调用 RAG 服务进行检索"""
    try:
        rag_config = PROMPTS.get('question_generation', {}).get('rag_config', {})
        rag_enabled = rag_config.get('enabled', False)
        
        if not rag_enabled:
            return []
        
        api_url = rag_config.get('api_url', 'http://localhost:3004/api/retrieve')
        response = requests.post(api_url, json={
            'query': query,
            'top_k': top_k
        }, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('results', [])
        else:
            print(f"RAG API error: {response.status_code}")
            return []
    except Exception as e:
        print(f"RAG retrieve error: {e}")
        return []

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

    # 从提示词文件获取配置
    interview_flow = PROMPTS.get('interview_flow', {})
    interviewer_role = PROMPTS.get('interviewer_role', {})
    
    # 构建系统提示词
    system_prompt = f"""你是一个专业的{position}岗位面试官，严格按照以下面试流程进行面试：

{interview_flow.get('system_prompt', '')}

面试流程：
"""
    
    # 添加流程步骤
    flow_steps = interview_flow.get('flow_steps', [])
    for step in flow_steps:
        system_prompt += f"{step.get('step')}. {step.get('name')}: {step.get('description')} (时长: {step.get('duration')})\n"
    
    # 添加控制规则
    system_prompt += "\n控制规则：\n"
    control_rules = interview_flow.get('control_rules', [])
    for rule in control_rules:
        system_prompt += f"- {rule}\n"
    
    # 添加面试官角色信息
    system_prompt += "\n面试官角色：\n"
    system_prompt += f"- 角色定位：{interviewer_role.get('role', '专业面试官')}\n"
    system_prompt += "- 性格特点：" + ", ".join(interviewer_role.get('personality', [])) + "\n"
    system_prompt += "- 沟通风格：" + ", ".join(interviewer_role.get('communication_style', [])) + "\n"
    
    # 添加响应策略
    system_prompt += "\n响应策略：\n"
    response_strategies = interviewer_role.get('response_strategies', [])
    for strategy in response_strategies:
        system_prompt += f"- {strategy}\n"
    
    # 添加禁忌话题
    system_prompt += "\n禁忌话题：\n"
    taboo_topics = interviewer_role.get('taboo_topics', [])
    for topic in taboo_topics:
        system_prompt += f"- {topic}\n"
    
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

    # 从提示词文件获取配置
    question_settings = PROMPTS.get('question_generation', {})
    default_settings = question_settings.get('default_settings', {})
    total_questions = default_settings.get('total_questions', 5)
    difficulty_distribution = default_settings.get('difficulty_distribution', {
        '简单': 2,
        '中等': 2,
        '困难': 1
    })

    # 调用 RAG 检索相关知识点
    rag_results = rag_retrieve(f"{position} 面试题 核心知识点", top_k=10)
    
    # 构建 RAG 知识上下文
    rag_context = ""
    if rag_results:
        rag_context = "基于以下知识点生成题目：\n"
        for i, result in enumerate(rag_results[:5]):  # 取前5个结果
            question = result.get('question', '')
            answer = result.get('answer', '')
            if question and answer:
                rag_context += f"{i+1}. 问题：{question}\n   答案：{answer}\n\n"

    # 构建默认提示词
    default_prompt = f"""{question_settings.get('system_prompt', '你是一个专业的题目生成器，根据岗位要求和 RAG 检索结果生成高质量的面试题目')}

{rag_context}

请为{position}岗位生成{total_questions}道面试题目，难度递增。

要求：
1. 题目涵盖该岗位的核心技能和知识点
2. 题目难度从简单到困难递增
3. 每道题目需要标明难度等级（简单、中等、困难）
4. 题目要具体、有针对性
5. 每个题目必须包含正确答案
6. 输出格式为JSON数组，包含{total_questions}个对象，每个对象包含id、difficulty、question、answer四个字段

示例输出格式：
[
  {{
    "id": 1,
    "difficulty": "简单",
    "question": "请解释什么是RESTful API",
    "answer": "RESTful API是一种软件架构风格，它定义了一组约束条件和原则，用于设计网络应用程序接口。REST（Representational State Transfer）的核心思想是使用HTTP协议的标准方法（GET、POST、PUT、DELETE等）来操作资源，通过URL来标识资源，使用JSON或XML等格式来传递数据。"
  }},
  ...
]
"""
    prompt = custom_prompt if custom_prompt else default_prompt

    response = client.chat.completions.create(
        model='deepseek-chat',
        messages=[
            {'role': 'system', 'content': 'You are an experienced interviewer. Generate interview questions with answers in JSON format based on the given position and RAG context.'},
            {'role': 'user', 'content': prompt + '\n\nPlease respond with valid JSON only.'},
        ],
        response_format={"type": "json_object"}
    )

    result = response.choices[0].message.content
    questions = json.loads(result)
    
    # 为每个题目生成关键点
    for question in questions:
        question['points'] = extract_key_points(question['answer'])
    
    # 保存带有关键点的题目到缓存文件
    cache_file = os.path.join(BASE_DIR, 'data', 'interview_questions_cache.json')
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)
    
    return jsonify(questions)


def extract_key_points(answer):
    """从答案中提取关键点"""
    if not answer:
        return {}
    
    # 使用 LLM 提取关键点
    prompt = f"""请从以下答案中提取5个最重要的关键点，每个关键点用简洁的短语表示：

{answer}

输出格式：一个JSON对象，键为数字1-5，值为对应的关键点

示例输出：
{{
  "1": "REST是一种软件架构风格",
  "2": "使用HTTP协议的标准方法",
  "3": "通过URL标识资源",
  "4": "使用JSON或XML传递数据",
  "5": "无状态通信"
}}
"""
    
    response = client.chat.completions.create(
        model='deepseek-chat',
        messages=[
            {'role': 'system', 'content': '你是一个专业的内容分析专家，擅长从文本中提取关键信息。'}, 
            {'role': 'user', 'content': prompt + '\n\n请直接输出JSON格式，不要包含其他文字。'}
        ],
        response_format={"type": "json_object"}
    )
    
    result = response.choices[0].message.content
    try:
        points = json.loads(result)
        return points
    except:
        # 如果提取失败，返回空对象
        return {}


@app.route('/api/extract-key-points', methods=['POST'])
def extract_key_points_api():
    """提取答案的关键点"""
    payload = request.get_json(force=True)
    answer = payload.get('answer', '').strip()
    
    if not answer:
        return jsonify({'error': 'Empty answer'}), 400
    
    points = extract_key_points(answer)
    return jsonify(points)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)