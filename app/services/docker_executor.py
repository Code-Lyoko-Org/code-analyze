"""Docker executor service for running target projects and executing tests."""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.models.schemas import ExecutionResult
from app.services.templates import NODEJS_TEST_SCRIPT, PYTHON_TEST_SCRIPT

# Configure logger
logger = logging.getLogger(__name__)


class DockerExecutor:
    """Service for executing tests in Docker containers."""

    def __init__(self):
        self.settings = get_settings()
        self._check_docker_available()

    def _check_docker_available(self) -> bool:
        """Check if Docker is available."""
        import subprocess
        try:
            result = subprocess.run(
                ["docker", "version"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"Docker not available: {e}")
            return False

    async def execute_tests(
        self,
        project_path: str,
        test_code: str,
        project_type: str = "nodejs",
        timeout: int = 300,
    ) -> ExecutionResult:
        """Execute generated test code in a Docker container.
        
        Args:
            project_path: Path to the extracted project
            test_code: Generated test code to execute
            project_type: "nodejs" or "python"
            timeout: Timeout in seconds
            
        Returns:
            ExecutionResult with test outcome and logs
        """
        try:
            if project_type == "nodejs":
                return await self._execute_nodejs_tests(
                    project_path, test_code, timeout
                )
            else:
                return await self._execute_python_tests(
                    project_path, test_code, timeout
                )
        except asyncio.TimeoutError:
            logger.error(f"Test execution timed out after {timeout} seconds")
            return ExecutionResult(
                tests_passed=False,
                log=f"测试执行超时（{timeout}秒）",
            )
        except Exception as e:
            logger.error(f"Test execution failed: {e}", exc_info=True)
            return ExecutionResult(
                tests_passed=False,
                log=f"测试环境初始化失败: {e}",
            )

    async def _execute_nodejs_tests(
        self,
        project_path: str,
        test_code: str,
        timeout: int,
    ) -> ExecutionResult:
        """Execute Node.js tests using Docker."""
        container_name = f"code-analyze-test-{os.getpid()}"
        
        # Use port 3000 inside the isolated container (no conflicts)
        port = 3000
        test_file = "generated_test.spec.js"
        
        # Normalize port references in test code to use localhost:3000
        test_code = test_code.replace("localhost:3001", f"localhost:{port}")
        test_code = test_code.replace("localhost:3002", f"localhost:{port}")
        
        # Write test file to project
        logger.info("      → Writing test file...")
        test_file_path = Path(project_path) / test_file
        test_file_path.write_text(test_code)
        
        # Create test runner script from template
        logger.info("      → Creating test runner script...")
        run_script = NODEJS_TEST_SCRIPT.format(port=port)
        
        run_script_path = Path(project_path) / "run_tests.sh"
        run_script_path.write_text(run_script)
        run_script_path.chmod(0o755)
        
        # Run Docker container (isolated network, no --network host)
        logger.info("      → Starting Docker container (node:18-alpine)...")
        docker_cmd = [
            "docker", "run",
            "--rm",
            "--name", container_name,
            "-v", f"{project_path}:/app",
            "-w", "/app",
            "node:18-alpine",
            "/bin/sh", "-c", "apk add --no-cache bash curl > /dev/null 2>&1 && bash /app/run_tests.sh"
        ]
        
        logger.info("      → Executing tests in container...")
        return await self._run_docker_command(docker_cmd, timeout, container_name)

    async def _execute_python_tests(
        self,
        project_path: str,
        test_code: str,
        timeout: int,
    ) -> ExecutionResult:
        """Execute Python tests using Docker."""
        container_name = f"code-analyze-test-{os.getpid()}"
        
        # Use port 8000 inside the isolated container
        port = 8000
        test_file = "generated_test.py"
        
        # Normalize port references
        test_code = test_code.replace("localhost:8001", f"localhost:{port}")
        
        # Write test file to project
        logger.info("      → Writing test file...")
        test_file_path = Path(project_path) / test_file
        test_file_path.write_text(test_code)
        
        # Create test runner script from template
        logger.info("      → Creating test runner script...")
        run_script = PYTHON_TEST_SCRIPT.format(port=port)
        
        run_script_path = Path(project_path) / "run_tests.sh"
        run_script_path.write_text(run_script)
        run_script_path.chmod(0o755)
        
        logger.info("      → Starting Docker container (python:3.11-slim)...")
        docker_cmd = [
            "docker", "run",
            "--rm",
            "--name", container_name,
            "-v", f"{project_path}:/app",
            "-w", "/app",
            "python:3.11-slim",
            "/bin/bash", "-c", "apt-get update > /dev/null && apt-get install -y curl > /dev/null && bash /app/run_tests.sh"
        ]
        
        logger.info("      → Executing tests in container...")
        return await self._run_docker_command(docker_cmd, timeout, container_name)

    async def _run_docker_command(
        self,
        docker_cmd: list,
        timeout: int,
        container_name: str,
    ) -> ExecutionResult:
        """Run Docker command and collect output."""
        process = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        
        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            full_log = stdout.decode("utf-8", errors="replace")
            
            # Extract just the test results portion for cleaner output
            log = self._extract_test_results(full_log)
            
            tests_passed = process.returncode == 0
            
            return ExecutionResult(
                tests_passed=tests_passed,
                log=log,
                error=None if tests_passed else "部分测试未通过"
            )
            
        except asyncio.TimeoutError:
            # Kill the container
            kill_process = await asyncio.create_subprocess_exec(
                "docker", "kill", container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await kill_process.wait()
            raise

    def _extract_test_results(self, full_log: str) -> str:
        """Extract the test results portion from the full log."""
        lines = full_log.split('\n')
        
        # Find the start of test output
        result_lines = []
        in_test_section = False
        
        for line in lines:
            # Skip ANSI color codes for cleaner output
            clean_line = self._strip_ansi(line)
            
            if "Running tests" in clean_line or "========== Running tests ==========" in clean_line:
                in_test_section = True
                continue
            
            if in_test_section:
                # Skip empty lines at the start
                if not result_lines and not clean_line.strip():
                    continue
                result_lines.append(clean_line)
        
        if result_lines:
            return '\n'.join(result_lines[-50:])  # Last 50 lines of test output
        
        # Fallback: return last 30 lines
        return '\n'.join([self._strip_ansi(l) for l in lines[-30:]])

    def _strip_ansi(self, text: str) -> str:
        """Remove ANSI escape codes from text."""
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    async def cleanup_container(self, container_name: str):
        """Clean up Docker container."""
        try:
            process = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await process.wait()
        except Exception as e:
            logger.warning(f"Failed to cleanup container {container_name}: {e}")


# Singleton instance
_docker_executor: Optional[DockerExecutor] = None


def get_docker_executor() -> DockerExecutor:
    """Get the DockerExecutor singleton."""
    global _docker_executor
    if _docker_executor is None:
        _docker_executor = DockerExecutor()
    return _docker_executor
