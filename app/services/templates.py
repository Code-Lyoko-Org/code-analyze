"""Shell script templates for Docker executor.

All shell scripts are centralized here for easy management.
Use .format() or string Template for variable substitution.
"""

# Node.js test runner script
NODEJS_TEST_SCRIPT = """#!/bin/bash
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


# Python test runner script
PYTHON_TEST_SCRIPT = """#!/bin/bash
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
