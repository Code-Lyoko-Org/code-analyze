"""LLM client using official OpenAI SDK."""

import json
import logging
from typing import List, Dict, Any, Optional

from openai import AsyncOpenAI
from langfuse import Langfuse

from app.config import get_settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for LLM API calls using OpenAI SDK."""

    def __init__(self):
        self.settings = get_settings()
        self.model = self.settings.llm_model
        
        # Initialize OpenAI client
        self.client = AsyncOpenAI(
            api_key=self.settings.llm_api_key,
        )
        
        # Initialize Langfuse for observability (optional)
        public_key = self.settings.langfuse_public_key
        secret_key = self.settings.langfuse_secret_key
        host = self.settings.langfuse_host
        
        if public_key and secret_key:
            self.langfuse = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
        else:
            self.langfuse = None

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        trace_name: str = "chat_completion",
    ) -> str:
        """Send a chat completion request using OpenAI SDK.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (default 1.0 for compatibility with all models)
            max_tokens: Maximum tokens to generate
            trace_name: Name for Langfuse trace
            
        Returns:
            The assistant's response content
        """
        try:
            # Build kwargs
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
            }
            
            # Only add temperature if not default (some models don't support it)
            if temperature != 1.0:
                kwargs["temperature"] = temperature
            
            if max_tokens:
                kwargs["max_tokens"] = max_tokens

            # Call OpenAI API
            response = await self.client.chat.completions.create(**kwargs)
            
            content = response.choices[0].message.content
            
            if not content:
                raise ValueError("LLM 返回空响应")
            
            # Log usage
            if response.usage:
                logger.info(f"LLM usage: {response.usage.prompt_tokens} + {response.usage.completion_tokens} tokens")
            
            return content
            
        except Exception as e:
            logger.error(f"LLM API error: {e}", exc_info=True)
            raise

    async def analyze_feature(
        self,
        feature_description: str,
        code_structure: str,
    ) -> Dict[str, Any]:
        """Analyze where a feature is implemented in the code.
        
        Args:
            feature_description: Description of the feature to locate
            code_structure: String representation of code structure
            
        Returns:
            Dict with implementation locations
        """
        system_prompt = """你是一个代码分析专家。你的任务是分析代码结构，定位实现特定功能的代码位置。

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

        user_prompt = f"""功能需求: {feature_description}

代码结构:
{code_structure}

请分析并定位实现该功能的代码位置。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"功能: {feature_description}\n\n代码结构:\n{code_structure}"},
        ]

        response = await self.chat_completion(
            messages, 
            trace_name=f"analyze_feature:{feature_description[:30]}"
        )
        
        # Parse JSON response
        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            return json.loads(response.strip())
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response as JSON: {response[:200]}")
            return {
                "feature_description": feature_description,
                "implementation_location": [],
            }

    async def extract_features(self, problem_description: str) -> List[str]:
        """Extract individual features from a problem description.
        
        Args:
            problem_description: Full problem/requirement description
            
        Returns:
            List of individual feature descriptions
        """
        system_prompt = """你是一个需求分析专家。从需求描述中提取**用户直接使用的业务功能**。

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

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"需求描述:\n{problem_description}"},
        ]

        response = await self.chat_completion(
            messages, 
            trace_name="extract_features"
        )
        
        # Parse JSON response
        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            features = json.loads(response.strip())
            if isinstance(features, list):
                return features
            return [features]
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse features as JSON: {response[:200]}")
            return [problem_description]

    async def generate_execution_plan(self, code_structure: str) -> str:
        """Generate an execution plan suggestion for the project.
        
        Args:
            code_structure: String representation of code structure
            
        Returns:
            Execution plan suggestion text
        """
        system_prompt = """你是一个项目部署专家。根据代码结构，生成如何运行该项目的建议。
输出简洁的执行步骤，不超过100字。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"代码结构:\n{code_structure}"},
        ]

        return await self.chat_completion(
            messages, 
            trace_name="generate_execution_plan"
        )

    async def generate_test_code(
        self,
        features_text: str,
        execution_plan: str,
        code_structure: str,
        project_type: str = "nodejs",
        schema_content: str = "",
    ) -> str:
        """Generate integration test code based on feature analysis.
        
        Args:
            features_text: Formatted feature analysis text
            execution_plan: How to run the project
            code_structure: Code structure string
            project_type: "nodejs" or "python"
            schema_content: GraphQL schema or API definition (for accurate query generation)
            
        Returns:
            Generated test code as string
        """
        if project_type == "nodejs":
            system_prompt = """你是一个测试工程师。你需要根据功能分析生成 Node.js 集成测试代码。

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
        else:
            system_prompt = """你是一个测试工程师。你需要根据功能分析生成 Python 集成测试代码。

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

        # Build user prompt with schema if available
        user_prompt = f"""功能分析结果：
{features_text}

项目运行方式：
{execution_plan}
"""
        
        if schema_content:
            user_prompt += f"""
**重要 - API Schema 定义（生成测试时必须严格遵循）：**
{schema_content[:6000]}
"""
        
        user_prompt += f"""
代码结构（部分）：
{code_structure[:2000]}

请生成覆盖以上功能的集成测试代码。确保 GraphQL 查询语法完全匹配 schema 定义。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = await self.chat_completion(
            messages,
            trace_name="generate_test_code"
        )
        
        # Clean up code block markers if present
        response = response.strip()
        if response.startswith("```javascript"):
            response = response[13:]
        if response.startswith("```python"):
            response = response[9:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
            
        return response.strip()

    async def fix_test_code(
        self,
        original_code: str,
        error_log: str,
        project_type: str = "nodejs",
    ) -> str:
        """Analyze test failure and fix the test code.
        
        Args:
            original_code: The original test code that failed
            error_log: Error log from test execution
            project_type: "nodejs" or "python"
            
        Returns:
            Fixed test code
        """
        system_prompt = f"""你是一个测试工程师。测试代码执行失败了，你需要分析错误并修复代码。

规则：
1. 仔细分析错误日志，找出失败原因
2. 常见问题：GraphQL 语法错误、变量名错误、断言错误、this.timeout 错误
3. 修复代码并返回完整的测试代码
4. 只输出修复后的代码，不要其他解释

如果错误是 "this.timeout is not a function"，请移除 this.timeout() 调用。"""

        user_prompt = f"""原始测试代码：
```
{original_code}
```

错误日志：
```
{error_log[-2000:]}
```

请分析错误并输出修复后的完整测试代码。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = await self.chat_completion(
            messages,
            trace_name="fix_test_code"
        )
        
        # Clean up code block markers
        response = response.strip()
        if response.startswith("```javascript"):
            response = response[13:]
        if response.startswith("```python"):
            response = response[9:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
            
        return response.strip()


# Singleton instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get the LLM client singleton."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
