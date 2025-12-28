# AI Code Reviewer

AI Agent 用于分析代码仓库并生成功能定位报告。

## 技术栈

- **Python 3.11** + FastAPI
- **Celery** + Redis (任务队列)
- **Tree-sitter** (AST 解析)
- **Qdrant** (向量存储)
- **OpenAI API 格式** LLM

## 快速开始

### 使用 Docker (推荐)

```bash
# 配置环境变量
cp .env.example .env
# 编辑 .env 设置 API_KEY

# 启动服务
docker compose up -d

# 测试
curl -X POST http://localhost:8000/api/review \
  -F "problem_description=Create a channel messaging system" \
  -F "code_zip=@your_code.zip"
```

### 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 启动 Redis 和 Qdrant
docker compose up -d redis qdrant

# 启动 Celery Worker
celery -A app.celery_app worker -l info

# 启动 FastAPI
uvicorn app.main:app --reload
```

## API

### POST /api/review

接收 `multipart/form-data`:
- `problem_description` (string): 功能需求描述
- `code_zip` (file): 代码压缩包

返回 JSON 分析报告。

## 输出示例

```json
{
  "feature_analysis": [
    {
      "feature_description": "实现建立频道功能",
      "implementation_location": [
        {
          "file": "src/modules/channel/channel.resolver.ts",
          "function": "createChannel",
          "lines": "13-16"
        }
      ]
    }
  ],
  "execution_plan_suggestion": "执行 npm install 后运行 npm run start:dev"
}
```
