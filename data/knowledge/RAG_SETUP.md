# RAG Knowledge Base Setup (Plan-Act-Review)

## Plan

目标：将 `data/knowledge` 下已完成 chunk 的知识数据，构建成可检索的 RAG 知识库。

产物：
- `data/knowledge/rag/rag_docs.jsonl`：标准化文档集合
- `data/knowledge/rag/rag_index.pkl`：向量索引（TF-IDF 或 OpenAI 向量）
- `backend/server/rag_server.py`：检索 API 服务
- `data/tools/query_rag.py`：本地命令行检索验证

## Act

### 1) 安装依赖

在项目根目录执行：

```bash
pip3 install -r backend/requirements.txt
```

### 2) 构建知识库（本地可直接跑）

```bash
python3 data/tools/build_rag_knowledge_base.py --backend tfidf
```

### 3) 本地检索验证

```bash
python3 data/tools/query_rag.py "什么是RAG" --top-k 5
```

### 4) 启动检索 API

```bash
python3 backend/server/rag_server.py
```

服务默认地址：`http://127.0.0.1:3001`

### 5) API 调用示例

```bash
curl -s -X POST http://127.0.0.1:3001/api/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"query":"什么是RAG","top_k":3}'
```

## Review

### 已完成验证

- 成功构建索引，文档数量：1600
- CLI 检索返回 Top-K 结果正常
- `/api/retrieve` 接口返回 JSON 正常

### 可选增强（下一步）

1. 切换到真实语义 embedding：

```bash
export EMBEDDING_API_KEY=你的Key
export EMBEDDING_API_BASE=https://api.openai.com/v1
python3 data/tools/build_rag_knowledge_base.py --backend openai --model text-embedding-3-small
```

2. 在 `llm_server.py` 中调用 `rag_server`，把检索结果拼接进 Prompt，实现完整 RAG 问答。
3. 增加重排器（reranker）提升 Top-K 质量。
4. 增加离线评估集（命中率、MRR、Recall@K）持续评估知识库质量。

## PostgreSQL + pgvector 方案（SQL TopK 检索）

### 目标架构

- PostgreSQL 存文档与元数据
- pgvector 存 embedding 向量
- 检索时用 SQL 做 TopK 相似度召回

### 1) 准备数据库与环境变量

```bash
export RAG_PG_DSN='postgresql://user:password@127.0.0.1:5432/aiinterview'
export EMBEDDING_API_KEY=你的Key
export EMBEDDING_API_BASE=https://api.openai.com/v1
export RAG_EMBEDDING_MODEL=text-embedding-3-small
```

### 2) 初始化表结构（包含 pgvector 扩展）

```bash
psql "$RAG_PG_DSN" -f data/tools/init_rag_pgvector.sql
```

### 3) 构建 embedding 并入库

```bash
python3 data/tools/build_rag_pgvector.py
```

### 4) 启动 pgvector 检索服务

```bash
export RAG_BACKEND=pgvector
python3 backend/server/rag_server.py
```

### 5) 调用检索 API

```bash
curl -s -X POST http://127.0.0.1:3001/api/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"query":"什么是RAG","top_k":3}'
```

### 说明

- 当前服务支持双模式：
  - `RAG_BACKEND=file`（默认）：读取 `data/knowledge/rag` 文件索引
  - `RAG_BACKEND=pgvector`：读取 PostgreSQL + pgvector
