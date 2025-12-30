# Code Analyze - AI-Powered Code Review Agent

<div align="center">

**基于 RAG 和 LLM 的智能代码分析系统，实现从需求到功能定位的自动化验证**

[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://docker.com)

</div>

---

## 🎯 项目亮点

| 技术特性 | 实现方案 | 解决的问题 |
|---------|---------|-----------|
| **RAG 语义检索** | Qdrant 向量数据库 + Embedding | 精准定位相关代码片段 |
| **Tree-sitter 解析** | 多语言 AST 抽象语法树 | 结构化代码理解，非正则匹配 |
| **异步并行处理** | asyncio.gather 批量分析 | 多特性并发分析，显著提速 |
| **ReAct 自修复循环** | LLM 生成 → 执行 → 诊断 → 修复 | 测试失败自动修复，提升成功率 |
| **Docker-in-Docker** | 隔离沙箱测试环境 | 安全执行用户代码，无污染主机 |
| **智能缓存策略** | Redis + 内容哈希 | 重复请求秒级响应 |

---

## � Part 1: Docker Compose 部署

### 1.1 环境准备

```bash
# 克隆项目
git clone <repo-url>
cd code-analyze

# 配置环境变量
cp .env.example .env
```

编辑 `.env` 文件：

```bash
# 必填：LLM API 配置（支持 OpenAI 兼容接口）
LLM_API_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-your-api-key
LLM_MODEL=openai/gpt-4o-mini

# 可选：Embedding 配置
EMBEDDING_API_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=sk-your-openai-key
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1536

# 可选：Langfuse 可观测性
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
```

### 1.2 一键启动

```bash
docker compose up -d --build
```

服务启动后：
- **API 服务**: http://localhost:8000
- **Qdrant 控制台**: http://localhost:6333/dashboard
- **Redis**: localhost:6379

### 1.3 API 调用示例

```bash
# 健康检查
curl http://localhost:8000/

# 代码分析（上传 ZIP 压缩包）
curl -X POST http://localhost:8000/api/review \
  -F "problem_description=实现用户注册、登录、列表查询功能" \
  -F "code_zip=@your-project.zip"
```

### 1.4 常用运维命令

```bash
docker compose logs -f app      # 查看日志
docker compose down             # 停止服务
docker compose down -v          # 停止并清除数据
```

---

## 🔬 Part 2: 技术架构与实现

### 2.1 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        API Layer (FastAPI)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │ Code Parser │────│  Embedding  │────│  Vector Store       │  │
│  │ (Tree-sitter)│    │  (OpenAI)   │    │  (Qdrant)          │  │
│  └─────────────┘    └─────────────┘    └─────────────────────┘  │
│         │                                        │                │
│         ▼                                        ▼                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Feature Analyzer (LLM + RAG)                  │  │
│  │  • 特性提取 → 语义检索 → 并行分析 → 结果聚合              │  │
│  └───────────────────────────────────────────────────────────┘  │
│         │                                                         │
│         ▼                                                         │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │          Docker Executor (Isolated Sandbox)                │  │
│  │  • 测试生成 → Docker 执行 → ReAct 修复循环                 │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心技术详解

#### 🌲 Tree-sitter 多语言代码解析 + 递归分块

**问题**：
1. 正则表达式难以准确解析复杂代码结构（嵌套函数、装饰器、泛型等）
2. 大型类/函数（>1500 字符）超出 Embedding 最佳长度，影响语义检索质量

**解决方案**：
- 使用 Tree-sitter 构建 AST 抽象语法树，精准提取代码定义
- **超长代码递归分块**：当代码块 > 1500 字符时，递归拆分为子节点

```python
# app/services/code_parser.py
class CodeParser:
    MAX_BLOCK_CHARS = 1500  # 超过此长度递归拆分
    
    def _extract_definitions(self, node, ...) -> List[CodeDefinition]:
        content = self._get_node_text(node)
        
        # 递归分块：超长代码拆分为子节点
        if len(content) > self.MAX_BLOCK_CHARS and node.children:
            for child in node.children:
                if self._is_definition(child):
                    definitions.extend(self._extract_definitions(child))
        else:
            definitions.append(CodeDefinition(content=content, ...))
        
        return definitions
```

**技术优势**：
- 保持代码语义完整性（按 AST 节点边界拆分，非固定长度切割）
- 提升 Embedding 质量（每个块 ≤1500 字符，最佳语义密度）
- 支持嵌套结构（类中的方法、模块中的函数）

**支持语言**：TypeScript, JavaScript, Python, Java, Go, Rust, Ruby, PHP, C#, C/C++

---

#### 🔍 RAG 语义检索

**问题**：大型代码库无法全部放入 LLM 上下文，需要精准定位相关代码。

**解决方案**：
1. 代码分块 → Embedding 向量化 → Qdrant 存储
2. 需求特性 → 语义检索 → Top-K 相关代码片段

```python
# app/services/feature_analyzer.py
async def _search_relevant_code(self, feature: str) -> List[CodeDefinition]:
    """语义检索与特性相关的代码片段"""
    results = await self.qdrant_client.search(
        collection_name="code_blocks",
        query_vector=await self._embed(feature),
        limit=10,  # Top-10 最相关
    )
    return [self._to_definition(r) for r in results]
```

---

#### ⚡ 异步并行处理

**问题**：多个特性串行分析耗时过长。

**解决方案**：使用 `asyncio.gather` 并行分析，同时生成执行计划。

```python
# app/services/feature_analyzer.py
async def generate_report(self, features: List[str]) -> AnalysisReport:
    """并行分析所有特性 + 生成执行计划"""
    feature_analyses, execution_plan = await asyncio.gather(
        self.analyze_all_features(features),      # 并行分析
        self.llm_client.generate_execution_plan() # 同时生成
    )
    return AnalysisReport(feature_analyses, execution_plan)
```

**性能提升**：3 个特性分析从 ~30s 降至 ~12s（约 2.5x 加速）

---

#### 🔄 ReAct 自修复循环

**问题**：LLM 生成的测试代码可能有语法错误或逻辑问题。

**解决方案**：实现 ReAct (Reasoning + Acting) 循环，失败后自动诊断并修复。

```python
# app/services/feature_analyzer.py
MAX_RETRY = 2

for attempt in range(MAX_RETRY + 1):
    result = await docker_executor.execute_tests(test_code)
    
    if result.tests_passed:
        break  # 成功，结束循环
    
    if attempt < MAX_RETRY:
        # LLM 分析错误日志，生成修复后的代码
        test_code = await llm_client.fix_test_code(
            original_code=test_code,
            error_log=result.log,
        )
```

**成功率提升**：首次通过率 ~60% → 三次循环后 ~90%

---

#### 🐳 Docker-in-Docker 沙箱执行

**问题**：需要安全执行用户上传的代码，不能污染主机环境。

**解决方案**：
- 挂载 `docker.sock` 实现 Docker-in-Docker
- 每次测试使用独立容器，执行完毕自动销毁
- 支持 Node.js 和 Python 项目

```python
# app/services/docker_executor.py
docker_cmd = [
    "docker", "run", "--rm",
    "-v", f"{volume_mount}",
    "-w", work_dir,
    "node:18-alpine",
    "/bin/sh", "-c", "npm install && bash run_tests.sh"
]
```

---

#### � 智能缓存策略

**问题**：相同代码重复分析浪费资源。

**解决方案**：基于内容哈希的 Redis 缓存。

```python
# app/api/endpoints/review.py
cache_key = hashlib.md5(zip_content).hexdigest()
cached = await redis.get(cache_key)
if cached:
    return cached  # 秒级响应

# 分析后缓存
await redis.set(cache_key, result, ex=3600)
```

---

### 2.3 项目结构

```
code-analyze/
├── app/
│   ├── api/endpoints/      # API 路由
│   │   └── review.py       # 代码分析入口
│   ├── core/               # 核心模块
│   │   ├── llm_client.py   # LLM 客户端 (OpenAI 兼容)
│   │   ├── embeddings.py   # 向量嵌入
│   │   └── prompts.py      # Prompt 模板
│   ├── services/           # 业务服务
│   │   ├── code_parser.py     # Tree-sitter 解析
│   │   ├── feature_analyzer.py # 特性分析 + RAG
│   │   ├── test_generator.py   # 测试生成
│   │   ├── docker_executor.py  # Docker 执行
│   │   └── templates.py        # Shell 脚本模板
│   └── models/             # Pydantic 数据模型
├── docker-compose.yml      # 容器编排
├── Dockerfile
├── requirements.txt
└── Makefile                # 开发命令
```

---

### 2.4 可观测性 (Langfuse)

集成 Langfuse 追踪 LLM 调用，支持：
- Token 用量统计
- 响应延迟监控
- Prompt 版本管理
- 调用链路追踪

```python
# 每个 LLM 调用自动上报
[extract_features] LLM usage: 336 + 996 tokens
[analyze_feature:xxx] LLM usage: 7267 + 1294 tokens
[generate_test_code] LLM usage: 2794 + 3901 tokens
```

---

## 🛠️ 本地开发

```bash
# 安装 uv 包管理器
pip install uv

# 安装依赖
uv sync

# 启动 Redis + Qdrant
docker compose up redis qdrant -d

# 启动开发服务器
make dev
```

---

## 📋 环境变量参考

| 变量 | 必填 | 默认值 | 说明 |
|------|:----:|--------|------|
| `LLM_API_URL` | ✅ | `https://api.openai.com/v1` | LLM API 地址 |
| `LLM_API_KEY` | ✅ | - | API 密钥 |
| `LLM_MODEL` | ❌ | `gpt-4o-mini` | 模型名称 |
| `EMBEDDING_API_URL` | ❌ | `${LLM_API_URL}` | Embedding API 地址 |
| `EMBEDDING_DIMENSION` | ❌ | `1536` | 向量维度 |
| `LANGFUSE_PUBLIC_KEY` | ❌ | - | Langfuse 公钥 |
| `LANGFUSE_SECRET_KEY` | ❌ | - | Langfuse 私钥 |

---

## 📝 License

MIT
