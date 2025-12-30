"""LLM Client using OpenAI-compatible API format with Langfuse observability."""

import os
import httpx
import json
import logging
from typing import List, Dict, Any, Optional

from langfuse import Langfuse

from app.config import get_settings
from app.core.prompts import (
    ANALYZE_FEATURE_SYSTEM,
    ANALYZE_FEATURE_USER,
    EXTRACT_FEATURES_SYSTEM,
    EXTRACT_FEATURES_USER,
    EXECUTION_PLAN_SYSTEM,
    EXECUTION_PLAN_USER,
    TEST_NODEJS_SYSTEM,
    TEST_PYTHON_SYSTEM,
    TEST_USER_TEMPLATE,
    TEST_USER_SCHEMA_TEMPLATE,
    TEST_USER_FOOTER,
    FIX_TEST_SYSTEM,
    FIX_TEST_USER,
)

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for OpenAI-compatible LLM API with Langfuse tracing."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.llm_api_url.rstrip("/")
        self.api_key = self.settings.llm_api_key
        self.model = self.settings.llm_model
        
        # Initialize Langfuse client
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY", self.settings.langfuse_public_key)
        secret_key = os.getenv("LANGFUSE_SECRET_KEY", self.settings.langfuse_secret_key)
        host = os.getenv("LANGFUSE_HOST", self.settings.langfuse_host)
        
        if public_key and secret_key:
            self.langfuse = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
            logger.info("Langfuse tracing enabled")
        else:
            self.langfuse = None

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        trace_name: str = "chat_completion",
    ) -> str:
        """Send a chat completion request to the LLM API."""
        # Build URL
        if self.base_url.endswith("/v1"):
            url = f"{self.base_url}/chat/completions"
        else:
            url = f"{self.base_url}/v1/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        
        if temperature != 1.0:
            payload["temperature"] = temperature
        
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
            
            if response.status_code != 200:
                logger.error(f"LLM API error: {response.status_code} - {response.text[:500]}")
            
            response.raise_for_status()
            
            if not response.content:
                raise ValueError("LLM API 返回空响应")
            
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"LLM API response not valid JSON: {response.text[:500]}")
                raise ValueError(f"LLM API 响应格式错误: {response.text[:100]}")
        
        if "choices" not in data or not data["choices"]:
            raise ValueError("LLM API 响应缺少 choices 字段")
        
        result = data["choices"][0]["message"]["content"]
        
        # End Langfuse generation with output
        if generation:
            generation.update(output=result)
            generation.end()
        
        # Log usage
        if "usage" in data:
            logger.info(f"[{trace_name}] LLM usage: {data['usage'].get('prompt_tokens', 0)} + {data['usage'].get('completion_tokens', 0)} tokens")

        return result

    async def analyze_feature(
        self,
        feature_description: str,
        code_structure: str,
    ) -> Dict[str, Any]:
        """Analyze where a feature is implemented in the code."""
        messages = [
            {"role": "system", "content": ANALYZE_FEATURE_SYSTEM},
            {"role": "user", "content": ANALYZE_FEATURE_USER.format(
                feature_description=feature_description,
                code_structure=code_structure
            )},
        ]

        response = await self.chat_completion(
            messages, 
            trace_name=f"analyze_feature:{feature_description[:30]}"
        )
        
        return self._parse_json_response(response, {
            "feature_description": feature_description,
            "implementation_location": [],
        })

    async def extract_features(self, problem_description: str) -> List[str]:
        """Extract individual features from a problem description."""
        messages = [
            {"role": "system", "content": EXTRACT_FEATURES_SYSTEM},
            {"role": "user", "content": EXTRACT_FEATURES_USER.format(
                problem_description=problem_description
            )},
        ]

        response = await self.chat_completion(
            messages, 
            trace_name="extract_features"
        )
        
        result = self._parse_json_response(response, [problem_description])
        return result if isinstance(result, list) else [result]

    async def generate_execution_plan(self, code_structure: str) -> str:
        """Generate an execution plan suggestion for the project."""
        messages = [
            {"role": "system", "content": EXECUTION_PLAN_SYSTEM},
            {"role": "user", "content": EXECUTION_PLAN_USER.format(
                code_structure=code_structure
            )},
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
        """Generate integration test code based on feature analysis."""
        system_prompt = TEST_NODEJS_SYSTEM if project_type == "nodejs" else TEST_PYTHON_SYSTEM

        user_prompt = TEST_USER_TEMPLATE.format(
            features_text=features_text,
            execution_plan=execution_plan
        )
        
        if schema_content:
            user_prompt += TEST_USER_SCHEMA_TEMPLATE.format(
                schema_content=schema_content[:6000]
            )
        
        user_prompt += TEST_USER_FOOTER.format(
            code_structure=code_structure[:2000]
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = await self.chat_completion(
            messages,
            trace_name="generate_test_code"
        )
        
        return self._clean_code_block(response)

    async def fix_test_code(
        self,
        original_code: str,
        error_log: str,
        project_type: str = "nodejs",
    ) -> str:
        """Analyze test failure and fix the test code."""
        messages = [
            {"role": "system", "content": FIX_TEST_SYSTEM},
            {"role": "user", "content": FIX_TEST_USER.format(
                original_code=original_code,
                error_log=error_log[-2000:]
            )},
        ]

        response = await self.chat_completion(
            messages,
            trace_name="fix_test_code"
        )
        
        return self._clean_code_block(response)

    def _parse_json_response(self, response: str, default: Any) -> Any:
        """Parse JSON from LLM response, handling code blocks."""
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
            return default

    def _clean_code_block(self, response: str) -> str:
        """Remove code block markers from response."""
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
