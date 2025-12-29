# AI Code Reviewer

AI Agent 用于分析代码仓库并生成功能定位报告。

## 技术栈

- **Python 3.11** + FastAPI
- **Celery** + Redis (任务队列)
- **Tree-sitter** (AST 解析)
- **Qdrant** (向量存储)
- **OpenAI API 格式** LLM
- **Docker** (测试执行环境)

## 快速开始

### 使用 Docker (推荐)

```bash
# 配置环境变量
cp .env.example .env
# 编辑 .env 设置 API_KEY

# 启动服务
docker compose up -d

# 测试 (基础分析)
curl -X POST http://localhost:8000/api/review \
  -F "problem_description=Create a channel messaging system" \
  -F "code_zip=@your_code.zip"

# 测试 (包含功能验证)
curl -X POST http://localhost:8000/api/review \
  -F "problem_description=Create a channel messaging system" \
  -F "code_zip=@your_code.zip" \
  -F "enable_verification=true"
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
- `problem_description` (string, required): 功能需求描述
- `code_zip` (file, required): 代码压缩包
- `skip_cache` (bool, optional): 跳过缓存强制重新处理
- `enable_verification` (bool, optional): 启用功能验证（生成并执行测试）

返回 JSON 分析报告。

## 输出示例

### 基础分析
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

### 包含功能验证 (enable_verification=true)
```json
{
  "feature_analysis": [...],
  "execution_plan_suggestion": "...",
  "functional_verification": {
    "generated_test_code": "const request = require('supertest');\n...",
    "execution_result": {
      "tests_passed": true,
      "log": "1 passing (2s)"
    }
  }
}
```
