"""LLM server component."""
import json
import os
import urllib.error
import urllib.request

from .configuration import configuration
from .configuration_entry import configuration_entry
from .component_ext_server import ext_server
from .component_registry import ComponentRegistry


class comp_server_llm(ext_server):
    _TEST_PROMPT = "How are you today?"
    _TIMEOUT = 10
    _INFERENCE_TIMEOUT = 120
    DEFAULT_INFERENCE_PATH = "/api/chat"

    def __init__(self) -> None:
        super().__init__(
            name="llm",
            api_url="",
            dependencies=[ComponentRegistry().get("network")],
            hint="run `jejune llm status-config`",
            configuration=configuration(
                configuration_entry("LLM_MODEL_URL",  hint="edit .jejune/env-secrets", source_file=".jejune/env-secrets"),
                configuration_entry("LLM_API_KEY",    hint="edit .jejune/env-secrets", source_file=".jejune/env-secrets"),
                configuration_entry("LLM_MODEL_NAME", hint="edit .jejune/env-secrets", source_file=".jejune/env-secrets"),
            ),
        )
        self.cli_name = self.name

    @staticmethod
    def infer_server_url(model_url: str) -> str:
        """Derive the OpenWebUI root URL from the Ollama base URL.

        OpenWebUI proxies Ollama at <root>/ollama, so the server root is obtained
        by stripping the /ollama suffix when present.  For a bare Ollama instance
        (no proxy) the two URLs are identical.
        """
        stripped = model_url.rstrip("/")
        if stripped.endswith("/ollama"):
            return stripped[: -len("/ollama")]
        return stripped

    @staticmethod
    def check_server(url: str) -> tuple[bool, str]:
        """Stage 1: does the server answer at the HTTPS level?"""
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=comp_server_llm._TIMEOUT) as resp:
                resp.read()
            return True, "ok"
        except urllib.error.HTTPError:
            return True, "ok"
        except urllib.error.URLError as e:
            return False, f"unreachable: {e.reason}"

    @staticmethod
    def check_auth(url: str, api_key: str) -> tuple[bool, str]:
        """Stage 2: is the API key valid? (GET /api/v1/auths/)."""
        auth = {"Authorization": f"BEARER {api_key}"}
        req = urllib.request.Request(f"{url}/api/v1/auths/", headers=auth)
        try:
            with urllib.request.urlopen(req, timeout=comp_server_llm._TIMEOUT) as resp:
                resp.read()
            return True, "ok"
        except urllib.error.URLError as e:
            return False, f"auth failed: {e.reason}"

    @staticmethod
    def check_model(url: str, api_key: str, model: str) -> tuple[bool, str]:
        """Stage 3: does the model exist on the server? (GET /api/models)."""
        auth = {"Authorization": f"BEARER {api_key}"}
        req = urllib.request.Request(f"{url}/api/models", headers=auth)
        try:
            with urllib.request.urlopen(req, timeout=comp_server_llm._TIMEOUT) as resp:
                data = json.loads(resp.read())
        except urllib.error.URLError as e:
            return False, f"model list unavailable: {e.reason}"
        except json.JSONDecodeError:
            return False, "model list: unexpected response format"

        models = [m.get("id", "") for m in data.get("data", [])]
        if model in models:
            return True, "ok"
        if models:
            shown = ", ".join(models[:5])
            suffix = f" … ({len(models)} total)" if len(models) > 5 else ""
            hint = f"available: {shown}{suffix}"
        else:
            hint = "no models returned"
        return False, f"model {model!r} not found — {hint}"

    @staticmethod
    def check_inference_endpoint(url: str, api_key: str, path: str) -> tuple[bool, str]:
        """Stage 4: does the inference endpoint accept POST? (empty body to probe the path)."""
        auth = {"Authorization": f"BEARER {api_key}"}
        req = urllib.request.Request(
            f"{url}{path}",
            data=b"{}",
            headers={**auth, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=comp_server_llm._TIMEOUT) as resp:
                resp.read()
            return True, "ok"
        except urllib.error.HTTPError as e:
            if e.code in (400, 422):
                return True, "ok"
            return False, f"endpoint error {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            return False, f"endpoint unreachable: {e.reason}"

    @staticmethod
    def check_inference(
        url: str, api_key: str, model: str, path: str, prompt: str = _TEST_PROMPT
    ) -> tuple[bool, str]:
        """Stage 5: does inference succeed? Uses OpenAI-compatible request body."""
        auth = {"Authorization": f"BEARER {api_key}"}
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            f"{url}{path}",
            data=payload,
            headers={**auth, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=comp_server_llm._INFERENCE_TIMEOUT) as resp:
                resp.read()
            return True, "ok"
        except urllib.error.HTTPError as e:
            return False, f"inference failed: {e.code} {e.reason}"
        except urllib.error.URLError as e:
            return False, f"inference failed: {e.reason}"
        except TimeoutError:
            return False, f"inference timed out after {comp_server_llm._INFERENCE_TIMEOUT}s"

    def _check_context(self) -> tuple[str, str, str, str, str] | None:
        """Resolve check parameters from env vars; return None when not fully configured."""
        url = (os.environ.get("LLM_MODEL_URL") or "").rstrip("/")
        api_key = os.environ.get("LLM_API_KEY") or ""
        model = os.environ.get("LLM_MODEL_NAME") or ""
        if not url or not api_key or not model:
            return None
        explicit = os.environ.get("LLM_SERVER_URL")
        server_url = explicit.rstrip("/") if explicit else self.infer_server_url(url)
        inference_path = os.environ.get("LLM_INFERENCE_ENDPOINT", self.DEFAULT_INFERENCE_PATH)
        return url, api_key, model, server_url, inference_path

    def available(self) -> tuple[bool, str]:
        """Quick availability check: server reachable and API key valid.

        Reads LLM_MODEL_URL, LLM_API_KEY, and optionally LLM_SERVER_URL from the
        environment.  Intended as a preflight guard before launching containers.
        Returns (False, "not configured") when required env vars are absent.
        """
        url     = (os.environ.get("LLM_MODEL_URL") or "").rstrip("/")
        api_key = os.environ.get("LLM_API_KEY") or ""
        if not url or not api_key:
            return False, "not configured"
        explicit = os.environ.get("LLM_SERVER_URL")
        server_url = explicit.rstrip("/") if explicit else self.infer_server_url(url)
        passed, msg = self.check_server(server_url)
        if not passed:
            return False, msg
        return self.check_auth(server_url, api_key)

    def check_availability(self) -> tuple[bool, str]:
        """Full 5-step availability check; consumed by catalog.run_all() and *-availability commands."""
        ctx = self._check_context()
        if ctx is None:
            return False, "not configured"
        url, api_key, model, server_url, inference_path = ctx
        for fn in (
            lambda: self.check_server(server_url),
            lambda: self.check_auth(server_url, api_key),
            lambda: self.check_model(server_url, api_key, model),
            lambda: self.check_inference_endpoint(url, api_key, inference_path),
            lambda: self.check_inference(url, api_key, model, inference_path),
        ):
            passed, msg = fn()
            if not passed:
                return False, msg
        return True, "ok"

    def check(self) -> tuple[str, str]:
        ok, msg = self.available()
        if ok:
            return "ok", ""
        return "warn" if msg == "not configured" else "error", msg


