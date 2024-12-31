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
			echo "Checking if port 5432 is already in use..."; \
			if sudo lsof -i :5432 >/dev/null 2>&1; then \
				echo "Port 5432 is in use. Checking if it is linked to the postgres_db container..."; \
				if docker inspect -f '{{.State.Pid}}' postgres_db | xargs -I{} sudo lsof -i :5432 -t | grep -q {}; then \
					echo "Stopping the offending process from the postgres_db container..."; \
					docker stop postgres_db; \
				else \
					echo "Error: Port 5432 is in use by another process. Please free the port and try again."; \
					exit 1; \
				fi; \
			fi; \
			echo "Starting existing PostgreSQL container..."; \
			docker start postgres_db; \
		else \
			echo "PostgreSQL container is already running."; \
		fi; \
	else \
		echo "Checking if port 5432 is already in use..."; \
		if lsof -i :5432 >/dev/null 2>&1; then \
			echo "Error: Port 5432 is already in use by another process. Please free the port or use a different port."; \
			exit 1; \
		else \
			echo "Creating a new PostgreSQL container..."; \
			docker run --name postgres_db \
				-e POSTGRES_DB=$(PROJECT_NAME) \
				-e POSTGRES_USER=app_user \
				-e POSTGRES_PASSWORD=app_pass \
				-p 5432:5432 \
				-d postgres; \
			sleep 5; \
			poetry run $(PYTHON_INTERPRETER) async_image_prediction/database/initialize_db.py; \
		fi; \
	fi

## Reset PostgreSQL database and schema
.PHONY: db-reset
db-reset:
	@if [ "$(shell docker ps -aq -f name=postgres_db)" ]; then \
		echo "Removing PostgreSQL container..."; \
		docker rm -f postgres_db; \
		sleep 2; \
	fi
	echo "Creating a fresh PostgreSQL container...";
	docker run --name postgres_db -e POSTGRES_DB=$(PROJECT_NAME) -e POSTGRES_USER=app_user -e POSTGRES_PASSWORD=app_pass -p 5432:5432 -d postgres;
	sleep 5
	poetry run $(PYTHON_INTERPRETER) async_image_prediction/database/initialize_db.py

## Start Redis server
.PHONY: start-redis
start-redis:
	redis-server &

## Start Celery worker
.PHONY: start-celery
start-celery:
	poetry run celery -A async_image_prediction.tasks.tasks worker --loglevel=info > celery.log 2>&1 &

## Restart Redis server
.PHONY: restart-redis
restart-redis:
	@sudo pkill redis-server || true
	make start-redis

## Restart Celery worker
.PHONY: restart-celery
restart-celery:
	@ps aux | grep 'celery' | grep -v 'grep' | awk '{print $$2}' | xargs kill -9 || true
	make start-celery

## Start FastAPI application
.PHONY: start-api
start-api:
	poetry run uvicorn async_image_prediction.api.app:app --reload #> api.log 2>&1 &

## Run all tools (Redis, Celery, FastAPI)
.PHONY: setup-all
setup-all: requirements db-init start-redis start-celery start-api

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
