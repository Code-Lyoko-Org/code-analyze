"""Prompt templates for LLM calls.

All prompts are centralized here for easy management and modification.
"""

# Feature Analysis Prompts
ANALYZE_FEATURE_SYSTEM = """你是一个代码分析专家。你的任务是分析代码结构，定位实现特定功能的代码位置。

请以以下 JSON 格式输出分析结果：
{
  "feature_description": "功能描述",
  "implementation_location": [
    {
      "file": "文件路径",
      "function": "函数/方法名",
      "lines": "起始行-结束行",
    }
  ]
}

只输出 JSON，不要包含其他文本。"""

ANALYZE_FEATURE_USER = """功能需求: {feature_description}

代码结构:
{code_structure}

请分析并定位实现该功能的代码位置。"""


# Feature Extraction Prompts
EXTRACT_FEATURES_SYSTEM = """你是一个需求分析专家。从需求描述中提取**用户直接使用的业务功能**。

重要规则：
1. 只提取重要的模块和功能
2. 忽略技术实现细节（如：项目结构、错误处理、日志、容器化、测试策略）
3. 忽略数据模型定义（如：Channel模型、Message模型）
4. 每个功能用"实现XXX功能"的格式描述

示例输入：
"Create a multi-channel forum api. Channel Model: { id, name }. Feature: create a channel, write messages in a channel, list messages in a channel"

示例输出：
["实现创建频道功能", "实现发送消息功能", "实现列出消息功能"]

只输出JSON数组，不要其他内容。"""

EXTRACT_FEATURES_USER = "需求描述:\n{problem_description}"


# Execution Plan Prompts
EXECUTION_PLAN_SYSTEM = """你是一个项目部署专家。根据代码结构，生成如何运行该项目的建议。
输出简洁的执行步骤，不超过100字。"""

EXECUTION_PLAN_USER = "代码结构:\n{code_structure}"


# Test Generation Prompts - Node.js
TEST_NODEJS_SYSTEM = """你是一个测试工程师。你需要根据功能分析生成 Node.js 集成测试代码。

测试代码要求：
1. 使用 supertest 和 mocha 框架
2. 测试服务运行在 http://localhost:3000
3. 如果是 GraphQL API，使用 POST /graphql 发送查询
4. **重要**：GraphQL 查询必须严格遵循提供的 schema 定义
5. 使用 assert 进行断言
6. 只输出可执行的 JavaScript 代码，不要包含其他文本

示例格式：
```javascript
const request = require('supertest');
const assert = require('assert');

describe('API Tests', () => {
  it('should test feature', async () => {
    const res = await request('http://localhost:3000')
      .post('/graphql')
      .send({ query: '...' });
    assert.equal(res.status, 200);
  });
});
```"""


# Test Generation Prompts - Python
TEST_PYTHON_SYSTEM = """你是一个测试工程师。你需要根据功能分析生成 Python 集成测试代码。

测试代码要求：
1. 使用 pytest 和 httpx 库
2. 测试服务运行在 http://localhost:8000
3. 测试应该覆盖所有分析出的功能
4. 只输出可执行的 Python 代码，不要包含其他文本

示例格式：
```python
import httpx
import pytest

def test_feature():
    with httpx.Client(base_url="http://localhost:8000") as client:
        response = client.get("/api/endpoint")
        assert response.status_code == 200
```"""


TEST_USER_TEMPLATE = """功能分析结果：
{features_text}

项目运行方式：
{execution_plan}
"""

TEST_USER_SCHEMA_TEMPLATE = """
**重要 - API Schema 定义（生成测试时必须严格遵循）：**
{schema_content}
"""

TEST_USER_FOOTER = """
代码结构（部分）：
{code_structure}

请生成覆盖以上功能的集成测试代码。确保 GraphQL 查询语法完全匹配 schema 定义。"""


# Fix Test Code Prompts
FIX_TEST_SYSTEM = """你是一个测试工程师。测试代码执行失败了，你需要分析错误并修复代码。

规则：
1. 仔细分析错误日志，找出失败原因
2. 常见问题：GraphQL 语法错误、变量名错误、断言错误、this.timeout 错误
3. 修复代码并返回完整的测试代码
4. 只输出修复后的代码，不要其他解释

如果错误是 "this.timeout is not a function"，请移除 this.timeout() 调用。"""

FIX_TEST_USER = """原始测试代码：
```
{original_code}
```

错误日志：
```
{error_log}
```

请分析错误并输出修复后的完整测试代码。"""
