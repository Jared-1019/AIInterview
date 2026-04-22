import os
from pathlib import Path
from flask import Flask, jsonify, send_file
import json

app = Flask(__name__)

# 缓存文件路径
BASE_DIR = Path(__file__).resolve().parents[2]
CACHE_FILE = os.path.join(BASE_DIR, 'data', 'interview_questions_cache.json')

@app.route('/')
def index():
    """显示缓存的面试题目"""
    if not os.path.exists(CACHE_FILE):
        return jsonify({
            'error': '缓存文件不存在',
            'message': '请先生成面试题目'
        }), 404
    
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            questions = json.load(f)
        return jsonify({
            'status': 'success',
            'data': questions,
            'count': len(questions)
        })
    except Exception as e:
        return jsonify({
            'error': '读取缓存文件失败',
            'message': str(e)
        }), 500

@app.route('/download')
def download():
    """下载缓存的JSON文件"""
    if not os.path.exists(CACHE_FILE):
        return jsonify({
            'error': '缓存文件不存在',
            'message': '请先生成面试题目'
        }), 404
    
    try:
        return send_file(CACHE_FILE, as_attachment=True, download_name='interview_questions_cache.json')
    except Exception as e:
        return jsonify({
            'error': '下载失败',
            'message': str(e)
        }), 500

@app.route('/status')
def status():
    """检查服务状态"""
    cache_exists = os.path.exists(CACHE_FILE)
    cache_size = os.path.getsize(CACHE_FILE) if cache_exists else 0
    
    return jsonify({
        'status': 'running',
        'cache_file': {
            'exists': cache_exists,
            'size': cache_size,
            'path': CACHE_FILE
        }
    })

if __name__ == '__main__':
    # 确保缓存目录存在
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    
    app.run(host='0.0.0.0', port=3005, debug=True)