# AIInterview

AI 驱动的面试模拟系统，基于 RAG（检索增强生成）和大语言模型技术，提供智能面试对话、语音交互、实时评估反馈等功能。

## 功能特性

### 🤖 智能面试对话
- 基于 DeepSeek LLM 的智能问答
- RAG 知识库增强回答
- 智能追问和深入探讨

### 🎤 语音交互
- 语音识别（Vosk 本地模型 + ASR 服务）
- 语音合成（gTTS）
- 实时语音通话面试

### 📊 面试评估
- 多维度评分体系（技术深度、逻辑表达、岗位匹配度等）
- 面试表达分析（语速、清晰度、自信度）
- 个性化改进建议
- 面试历史记录

## 技术架构

### 前端
- Vue.js 3
- 原生 JavaScript
- CSS3

### 后端
- Python Flask
- DeepSeek API (LLM)
- PostgreSQL + pgvector (向量数据库)
- Vosk (本地语音识别模型)
- gTTS / ASR / TTS 服务

## 项目结构

```
AIInterview/
├── frontend/              # 前端应用
│   ├── app.js            # Vue 应用主逻辑
│   ├── index.html        # 入口页面
│   └── style.css         # 样式文件
├── backend/              # 后端服务
│   ├── server/           # API 服务
│   │   ├── llm_server.py      # LLM 对话服务
│   │   ├── rag_server.py      # RAG 检索服务
│   │   ├── asr_server.py      # 语音识别服务
│   │   ├── tts_server.py      # 语音合成服务
│   │   └── phone_server.py    # 电话服务
│   ├── model/            # Vosk 语音模型
│   ├── requirements.txt  # Python 依赖
│   └── start_backend.sh  # 后端启动脚本
├── data/                 # 数据目录
│   ├── knowledge/        # 知识库
│   │   └── rag/          # RAG 索引和文档
│   └── tools/            # 数据处理工具
├── images/               # 静态资源
└── README.md
```

## 快速开始

### 环境要求
- Python 3.8+
- Node.js 16+ (可选，用于前端开发)
- PostgreSQL 14+ (启用 pgvector 扩展)

### 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 配置

1. 设置环境变量或修改 `server/llm_server.py` 中的 API Key
2. 配置 PostgreSQL 数据库连接

### 启动后端服务

```bash
cd backend
./start_backend.sh
# 或手动启动各服务
python server/llm_server.py
python server/rag_server.py
python server/asr_server.py
python server/tts_server.py
```

### 启动前端

直接用浏览器打开 `frontend/index.html`，或使用静态文件服务器：

```bash
cd frontend
python -m http.server 8080
```

然后访问 http://localhost:8080

## 知识库构建

使用 `data/tools/` 下的工具构建 RAG 知识库：

```bash
cd data/tools
python clean_knowledge_json.py      # 清洗知识数据
python chunk_knowledge_json.py      # 分块处理
python build_rag_knowledge_base.py  # 构建向量索引
python build_rag_pgvector.py        # 导入 PostgreSQL
```

## License

MIT
