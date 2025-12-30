# Code Analyze - AI Code Review Agent

一个基于 LLM 的代码分析 Agent，能够接收代码和需求，分析代码结构，并输出结构化的功能定位报告。

## 🚀 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 OpenAI API Key：

```bash
LLM_API_KEY=sk-your-openai-key-here
LLM_MODEL=gpt-4o-mini
```

### 2. 启动服务

```bash
docker compose up -d --build
```

### 3. 测试 API

```bash
# 检查服务状态
curl http://localhost:8000/

# 分析代码
curl -X POST http://localhost:8000/api/review \
  -F "problem_description=Create a multi-channel forum API with features: create channel, send message, list messages" \
  -F "code_zip=@your-project.zip"
```

## 📚 API 说明

### POST /api/review

分析代码并生成功能定位报告。

**请求参数：**
- `problem_description` (string): 需求描述
- `code_zip` (file): 项目 ZIP 压缩包

**响应示例：**
```json
{
  "success": true,
  "report": {
    "feature_analysis": [
      {
        "feature_description": "实现创建频道功能",
        "implementation_location": [
          {
            "file": "src/modules/channel/channel.service.ts",
            "function": "create",
            "lines": "21-24"
          }
        ]
      }
    ],
    "execution_plan_suggestion": "npm install && npm run start:dev",
    "functional_verification": {
      "generated_test_code": "...",
      "execution_result": {
        "tests_passed": true,
        "log": "4 passing (72ms)"
      }
    }
  }
}
```

## 🔧 技术栈

- **后端**: FastAPI + Python 3.11
- **LLM**: OpenAI GPT-4o-mini / GPT-4o
- **向量数据库**: Qdrant
- **缓存**: Redis
- **测试执行**: Docker-in-Docker
- **可观测性**: Langfuse (可选)

## 📁 项目结构

```
app/
├── api/endpoints/      # API 端点
├── core/               # 核心模块 (LLM, Embeddings, Prompts)
├── models/             # 数据模型
└── services/           # 业务服务
    ├── code_parser.py     # 代码解析 (Tree-sitter)
    ├── docker_executor.py # 测试执行
    ├── feature_analyzer.py # 功能分析
    └── ...
```

## 🛠️ 开发

### 本地开发

```bash
# 安装依赖
pip install uv
uv sync

# 启动依赖服务
docker compose up redis qdrant -d

# 启动开发服务器
make dev
```

### 常用命令

```bash
make dev          # 启动开发服务器
make test         # 运行测试
make clear-cache  # 清理缓存
```

## 📋 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `LLM_API_KEY` | ✅ | - | OpenAI API Key |
| `LLM_MODEL` | ❌ | `gpt-4o-mini` | LLM 模型 |
| `EMBEDDING_MODEL` | ❌ | `text-embedding-3-small` | Embedding 模型 |
| `LANGFUSE_PUBLIC_KEY` | ❌ | - | Langfuse 公钥 |
| `LANGFUSE_SECRET_KEY` | ❌ | - | Langfuse 私钥 |

## 📝 License

MIT
