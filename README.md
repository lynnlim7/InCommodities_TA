# InCommodities_TA

## Overview


## Requirements 

## Assumptions 

## Architecture

## Key Design Decisions 

### Decision 1 
Choice: 
Reason: 
Alternative:
Trade-off: 

### Decision 2

## Error Handling 

## Performance/ Complexity 

## Limitations 

## Getting Started 
1. Install dependencies 
Project uses `uv` for dependency management. 
The exact dependency versions are recorded in `uv.lock`.
Run: 
```bash 
uv sync 
```
This will create a `.venv` environment

2. Run application 
```bash 
uv run python <entrypoint>
```

3. Run tests 
Run the complete test suite: 
```bash 
uv run pytest
```

4. Code quality checks 
Run the linter: 
```bash 
uv run ruff check .
```
Run static type checking: 
```bash 
uv run mypy src
```