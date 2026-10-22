set positional-arguments

setup:
    uv sync --locked --no-install-project --python python3.12

build:
    python -m vault build

validate:
    python -m vault validate
