"""Docker executor service for running target projects and executing tests."""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.models.schemas import ExecutionResult

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
                return await self._execute_nodejs_tests(project_path, test_code, timeout)
            else:
                return await self._execute_python_tests(project_path, test_code, timeout)
        except asyncio.TimeoutError:
            logger.error(f"Test execution timed out after {timeout} seconds")
            return ExecutionResult(
                tests_passed=False,
                log="测试执行超时",
                error=f"测试执行超时（{timeout}秒）"
            )
        except Exception as e:
            logger.error(f"Test execution failed: {e}", exc_info=True)
            return ExecutionResult(
                tests_passed=False,
                log="测试执行失败",
                error="测试环境初始化失败，请检查 Docker 配置"
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
        
        # Normalize port references in test code to use localhost:3000
        test_code = test_code.replace("localhost:3001", f"localhost:{port}")
        test_code = test_code.replace("localhost:3002", f"localhost:{port}")
        
        # Write test file to project
        test_file_path = Path(project_path) / "generated_test.spec.js"
        test_file_path.write_text(test_code)
        logger.info(f"Written test file to {test_file_path}")
        
        # Create a script to run tests
        # Note: NestJS respects the PORT env var, and we wait for /graphql endpoint
        run_script = f"""#!/bin/bash
set -e

cd /app

# Install dependencies
echo "Installing dependencies..."
npm install --legacy-peer-deps 2>&1 | tail -5

# Install test dependencies
npm install --save-dev supertest mocha 2>&1 | tail -3

# Start the server in background
echo "Starting server on port {port}..."
PORT={port} npm run start:dev > /tmp/server.log 2>&1 &
SERVER_PID=$!

# Wait for server to be ready (check /graphql endpoint)
echo "Waiting for server..."
MAX_WAIT=90
for i in $(seq 1 $MAX_WAIT); do
    # Check if server is responding
    if curl -s -o /dev/null -w "%{{http_code}}" http://127.0.0.1:{port}/graphql 2>/dev/null | grep -q "400\\|200"; then
        echo "Server is ready after $i seconds!"
        break
    fi
    # Also check if process died
    if ! kill -0 $SERVER_PID 2>/dev/null; then
        echo "Server process died!"
        cat /tmp/server.log
        exit 1
    fi
    sleep 1
done

# Extra wait for full initialization
sleep 2

# Run the tests
echo "========== Running tests =========="
npx mocha generated_test.spec.js --timeout 30000 2>&1
TEST_EXIT_CODE=$?

# Cleanup
kill $SERVER_PID 2>/dev/null || true

exit $TEST_EXIT_CODE
"""
        
        run_script_path = Path(project_path) / "run_tests.sh"
        run_script_path.write_text(run_script)
        run_script_path.chmod(0o755)
        
        # Run Docker container (isolated network, no --network host)
        docker_cmd = [
            "docker", "run",
            "--rm",
            "--name", container_name,
            "-v", f"{project_path}:/app",
            "-w", "/app",
            "node:18-alpine",
            "/bin/sh", "-c", "apk add --no-cache bash curl > /dev/null 2>&1 && bash /app/run_tests.sh"
        ]
        
        logger.info(f"Running Docker command: {' '.join(docker_cmd[:6])}...")
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
        
        # Normalize port references
        test_code = test_code.replace("localhost:8001", f"localhost:{port}")
        
        # Write test file to project
        test_file_path = Path(project_path) / "generated_test.py"
        test_file_path.write_text(test_code)
        
        # Create a script to run tests
        run_script = f"""#!/bin/bash
set -e

cd /app

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt 2>&1 | tail -5 || true
pip install pytest pytest-asyncio httpx 2>&1 | tail -3

# Start the server in background
echo "Starting server on port {port}..."
if [ -f "manage.py" ]; then
    python manage.py runserver 0.0.0.0:{port} > /tmp/server.log 2>&1 &
elif [ -f "app/main.py" ]; then
    uvicorn app.main:app --host 0.0.0.0 --port {port} > /tmp/server.log 2>&1 &
else
    python -m uvicorn main:app --host 0.0.0.0 --port {port} > /tmp/server.log 2>&1 &
fi
SERVER_PID=$!

# Wait for server
echo "Waiting for server..."
for i in $(seq 1 30); do
    if curl -s http://127.0.0.1:{port} > /dev/null 2>&1; then
        echo "Server is ready!"
        break
    fi
    sleep 1
done

sleep 2

# Run tests
echo "========== Running tests =========="
pytest generated_test.py -v 2>&1
TEST_EXIT_CODE=$?

kill $SERVER_PID 2>/dev/null || true
exit $TEST_EXIT_CODE
"""
        
        run_script_path = Path(project_path) / "run_tests.sh"
        run_script_path.write_text(run_script)
        run_script_path.chmod(0o755)
        
        docker_cmd = [
            "docker", "run",
            "--rm",
            "--name", container_name,
            "-v", f"{project_path}:/app",
            "-w", "/app",
            "python:3.11-slim",
            "/bin/bash", "-c", "apt-get update > /dev/null && apt-get install -y curl > /dev/null && bash /app/run_tests.sh"
        ]
        
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
