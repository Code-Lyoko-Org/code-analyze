.PHONY: install dev celery test clean docker-deps clear-cache help

# Default target
help:
	@echo "Available commands:"
	@echo "  make install      - Install dependencies with uv"
	@echo "  make dev          - Start FastAPI development server"
	@echo "  make celery       - Start Celery worker"
	@echo "  make test         - Run tests"
	@echo "  make docker-deps  - Start Redis and Qdrant with Docker"
	@echo "  make clear-cache  - Clear Redis cache and Qdrant collection"
	@echo "  make clean        - Clean up cache files"

# Install dependencies
install:
	uv sync

# Start FastAPI development server
dev:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Start Celery worker
celery:
	uv run celery -A app.celery_app worker -l info -c 4

# Run tests
test:
	uv run pytest tests/ -v

# Start Docker dependencies (Redis + Qdrant)
docker-deps:
	@docker ps -q -f name=my-redis > /dev/null || docker run -d --name my-redis -p 6379:6379 redis:7-alpine
	@docker ps -q -f name=qdrant > /dev/null || docker run -d --name qdrant -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant:latest
	@echo "Redis and Qdrant are running"

# Stop Docker dependencies
docker-stop:
	-docker stop qdrant my-redis
	-docker rm qdrant my-redis

# Clear Redis cache and Qdrant collection
clear-cache:
	@docker exec my-redis redis-cli FLUSHDB
	@curl -s -X DELETE http://localhost:6333/collections/code_blocks > /dev/null
	@echo "Cache cleared: Redis flushed, Qdrant collection deleted"

# Clean up
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache 2>/dev/null || true

# Full development setup
setup: docker-deps install
	@echo "Setup complete! Run 'make dev' to start the server"
