.PHONY: install lint format test clean run baseline

install:
	uv sync --group dev

lint:
	uv run ruff check .

format:
	uv run ruff format .
	uv run ruff check . --fix

test:
	uv run pytest -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run:
	uv run python main.py

baseline:
	mkdir -p tests/logs; \
	LOG_FILE=tests/logs/baseline_`date "+%Y%m%d_%H%M%S"`.log; \
	TMP_FILE=$$(mktemp); \
	echo "===== Baseline run at `date '+%Y-%m-%d %H:%M:%S'` =====" | tee $$LOG_FILE; \
	echo "===== uv run pytest -q 结果 =====" | tee -a $$LOG_FILE; \
	uv run pytest -q > $$TMP_FILE 2>&1 || true; \
	tee -a $$LOG_FILE < $$TMP_FILE; \
	echo -e "\n===== uv run pytest --cov 完整覆盖率结果 =====" | tee -a $$LOG_FILE; \
	uv run pytest --cov=app --cov-report=term-missing --durations=15 > $$TMP_FILE 2>&1 || true; \
	tee -a $$LOG_FILE < $$TMP_FILE; \
	rm -f $$TMP_FILE; \
	echo "✅ 基线日志已保存至: $$LOG_FILE"