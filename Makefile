#################################################################################
# GLOBALS                                                                       #
#################################################################################

PROJECT_NAME = image_prediction
PYTHON_VERSION = 3.12
PYTHON_INTERPRETER = python

#################################################################################
# COMMANDS                                                                      #
#################################################################################

## Install Python Dependencies
.PHONY: requirements
requirements:
	poetry install

## Delete all compiled Python files
.PHONY: clean
clean:
	find . -type f -name "*.py[co]" -delete
	find . -type d -name "__pycache__" -delete

## Lint using flake8 and black
.PHONY: lint
lint:
	poetry run flake8 async_image_prediction
	poetry run black --check --config pyproject.toml async_image_prediction

## Format source code with black
.PHONY: format
format:
	poetry run black --config pyproject.toml async_image_prediction

## Initialize PostgreSQL database and schema
.PHONY: db-init
db-init:
	@if docker ps -aq -f name=postgres_db | grep -q .; then \
		if [ "$$(docker inspect -f '{{.State.Running}}' postgres_db)" = "false" ]; then \
			echo "Checking if port 5433 (host) is already in use..."; \
			if sudo lsof -i :5433 >/dev/null 2>&1; then \
				echo "Killing process on port 5433 (host)..."; \
				sudo lsof -t -i:5433 | xargs -r sudo kill -9; \
			fi; \
			echo "Checking if port 5432 (container) is already in use..."; \
			if sudo lsof -i :5432 >/dev/null 2>&1; then \
				echo "Killing process on port 5432 (container)..."; \
				sudo lsof -t -i:5432 | xargs -r sudo kill -9; \
			fi; \
			echo "Starting existing PostgreSQL container..."; \
			docker start postgres_db; \
		else \
			echo "PostgreSQL container is already running."; \
		fi; \
	else \
		echo "Checking if port 5433 (host) is already in use..."; \
		if sudo lsof -i :5433 >/dev/null 2>&1; then \
			echo "Killing process on port 5433 (host)..."; \
			sudo lsof -t -i:5433 | xargs -r sudo kill -9; \
		fi; \
		echo "Checking if port 5432 (container) is already in use..."; \
		if sudo lsof -i :5432 >/dev/null 2>&1; then \
			echo "Killing process on port 5432 (container)..."; \
			sudo lsof -t -i:5432 | xargs -r sudo kill -9; \
		fi; \
		echo "Creating a new PostgreSQL container..."; \
		docker run --name postgres_db \
			-e POSTGRES_DB=$(PROJECT_NAME) \
			-e POSTGRES_USER=app_user \
			-e POSTGRES_PASSWORD=app_pass \
			-p 5433:5432 \
			-d postgres; \
		sleep 5; \
		poetry run $(PYTHON_INTERPRETER) async_image_prediction/database/initialize_db.py; \
	fi

## Reset PostgreSQL database and schema
.PHONY: db-reset
db-reset:
	@echo "Resetting PostgreSQL database..."
	@docker rm -f postgres_db || true
	@make db-init

## Start Redis server
.PHONY: start-redis
start-redis:
	@if ! sudo lsof -i:6379 >/dev/null 2>&1; then \
		echo "Starting Redis server..."; \
		redis-server & \
	else \
		echo "Redis server is already running."; \
	fi

## Start Celery worker
.PHONY: start-celery
start-celery:
	#@@ps aux | grep 'celery' | grep -v 'grep' | awk '{print $$2}' | xargs -r kill -9 || true
	@echo "Starting Celery worker..."
	@poetry run celery -A async_image_prediction.tasks.tasks worker --loglevel=info > celery.log 2>&1 &

## Start FastAPI application
.PHONY: start-api
start-api:
	@if ! sudo lsof -i:8080 >/dev/null 2>&1; then \
		echo "Starting FastAPI server..."; \
		poetry run uvicorn async_image_prediction.api.app:app --reload --host 0.0.0.0 --port 8080; \
	else \
		echo "FastAPI server is already running."; \
	fi

## Stop all app services
.PHONY: shutdown
shutdown:
	@echo "Stopping all services..."
	@pgrep -f 'uvicorn' | xargs -r sudo kill -9 || true
	@pgrep -f 'celery' | xargs -r sudo kill -9 || true
	@pgrep -f 'redis-server' | xargs -r sudo kill -9 || true
	@docker stop postgres_db || true
	@echo "All services stopped."

## Restart all app services
.PHONY: restart-all
restart-all: shutdown
	make setup-all

## Run all tools (Redis, Celery, FastAPI)
.PHONY: setup-all
setup-all: 
	make requirements
	make db-init
	make start-redis
	make start-celery
	make start-api

#################################################################################
# Self Documenting Commands                                                     #
#################################################################################

.DEFAULT_GOAL := help

define PRINT_HELP_PYSCRIPT
import re, sys; \
lines = '\n'.join([line for line in sys.stdin]); \
matches = re.findall(r'\n## (.*)\n[\s\S]+?\n([a-zA-Z_-]+):', lines); \
print('Available rules:\n'); \
print('\n'.join(['{:25}{}'.format(*reversed(match)) for match in matches]))
endef
export PRINT_HELP_PYSCRIPT

## Show available commands
.PHONY: help
help:
	@$(PYTHON_INTERPRETER) -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)