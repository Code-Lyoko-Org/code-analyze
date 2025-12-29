"""LLM Client using OpenAI-compatible API format with Langfuse observability."""

import os
import httpx
import json
import logging
from typing import List, Dict, Any, Optional

from langfuse import Langfuse

from app.config import get_settings

# Configure logger
logger = logging.getLogger(__name__)


class LLMClient:
    """Client for OpenAI-compatible LLM API with Langfuse tracing."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.llm_api_url.rstrip("/")
        self.api_key = self.settings.llm_api_key
        self.model = self.settings.llm_model
        
        # Initialize Langfuse client using os.getenv (Langfuse reads these directly)
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY", self.settings.langfuse_public_key)
        secret_key = os.getenv("LANGFUSE_SECRET_KEY", self.settings.langfuse_secret_key)
        host = os.getenv("LANGFUSE_HOST", self.settings.langfuse_host)
        
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
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        trace_name: str = "chat_completion",
    ) -> str:
        """Send a chat completion request to the LLM API.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            trace_name: Name for Langfuse trace
            
        Returns:
            The assistant's response content
        """
        url = f"{self.base_url}/v1/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens

        # Create Langfuse generation if available
        generation = None
        if self.langfuse:
            generation = self.langfuse.start_generation(
                name=trace_name,
                model=self.model,
                input=messages,
                model_parameters={"temperature": temperature},
            )

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            # Log response status for debugging
            if response.status_code != 200:
                logger.error(f"LLM API error: {response.status_code} - {response.text[:500]}")
            
            response.raise_for_status()
            
            # Handle empty response
            if not response.content:
                logger.error("LLM API returned empty response")
                raise ValueError("LLM API 返回空响应")
            
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"LLM API response not valid JSON: {response.text[:500]}")
                raise ValueError(f"LLM API 响应格式错误: {response.text[:100]}")
        
        if "choices" not in data or not data["choices"]:
            logger.error(f"LLM API response missing choices: {data}")
            raise ValueError("LLM API 响应缺少 choices 字段")
        
        result = data["choices"][0]["message"]["content"]
        
        # End Langfuse generation with output
        if generation:
            generation.update(output=result)
            generation.end()
        
        return result

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
      "reason": "为什么这段代码实现了该功能"
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
            {"role": "user", "content": user_prompt},
        ]

        response = await self.chat_completion(
            messages, 
            temperature=0.3, 
            trace_name=f"analyze_feature:{feature_description[:30]}"
        )
        
        # Parse JSON from response
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
            return {
                "feature_description": feature_description,
                "implementation_location": [],
                "error": "Failed to parse LLM response"
            }

    async def extract_features(self, problem_description: str) -> List[str]:
        """Extract individual features from a problem description.
        
        Args:
            problem_description: The full problem/requirement description
            
        Returns:
            List of individual feature descriptions
        """
        system_prompt = """你是一个需求分析专家。从给定的需求描述中提取独立的功能点。

请以 JSON 数组格式输出功能列表，每个元素是一个功能描述字符串。
例如: ["创建频道", "发送消息", "列出消息"]

只输出 JSON 数组，不要包含其他文本。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"需求描述:\n{problem_description}"},
        ]

        response = await self.chat_completion(
            messages, 
            temperature=0.3,
            trace_name="extract_features"
        )
        
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
            temperature=0.5,
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
4. **重要**：GraphQL 查询必须严格遵循提供的 schema 定义，包括：
   - Mutation/Query 名称必须完全匹配
   - Input 参数名称必须完全匹配（如 createChannelInput 不能写成 input）
   - 字段类型必须正确（Int vs String）
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
        
        # Add schema content if available (important for accurate GraphQL queries)
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
            temperature=0.3,
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


# Singleton instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get the LLM client singleton."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
