# Code Style & Tooling

- Always format Python files using `uv run black <file_path>`
- Never use bare `black` without `uv run`

- When working in a git repository using python, never use bare `python`
  command. Instead use a python version that is compatible with the
  python versions specified in the technical requirements of the project
  (e.g. `pyproject.toml` or the `Readme.md`) e.g. python3.10 or by default
  python3 (but never a bare python).
