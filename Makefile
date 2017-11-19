.DEFAULT_GOAL := help

help: ## Display this help message
	@echo "Please use \`make <target>' where <target> is one of"
	@perl -nle'print $& if m{^[\.a-zA-Z_-]+:.*?## .*$$}' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m  %-25s\033[0m %s\n", $$1, $$2}'

requirements: ## Install requirements
	pip3 install -r requirements.txt

format: ## Auto-format to PEP8
	autopep8 --in-place --aggressive --aggressive app/*.py

env: ## Build virtual environment
	virtualenv -p `which python3.6` venv

docker: ## Run docker version interactively
	docker build -t tuchfarber/thatbeangame_dev .
	docker run -it -p 8080:8080 -e TBG_CLIENT_ORIGIN="http://localhost:8000" tuchfarber/thatbeangame_dev

api_doc: ## Builds API doc from TBG.py
	python ./docs/api_doc_builder.py

run: ## Run server
	@echo "For cross origin to work correctly make sure to set environment variable TBG_CLIENT_ORIGIN to your client's domain and port (e.g export TBG_CLIENT_ORIGIN='http://example.com:9091')"
	python -m py_compile app/*.py
	mypy --ignore-missing-imports  app/TBG.py
	TBG_CLIENT_ORIGIN='http://192.168.1.121:8000' python app/TBG.py

