## Formatting

This project uses **black** (configuration in `pyproject.toml`). Never manually reformat lines.
After modifying any Python file run `black <file>` before considering the change complete.

---

When this directory appears under
- `.jejune/tmp/`, or 
- `~/.local/share/uv/tools/jejune-cli/lib/python<version-number>/site-packages/`
then it is a managed clone maintained by jejune_cli or uv. Do NOT edit files there !
  Instead, look for the source repository that could be in
  - `@jejune_cli/` (in Claude Code is a chat/prompt terminology)
  - `@../jejune_cli` or
  - `~/tmp/jejune`
