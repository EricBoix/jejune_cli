"""Deployer-role heuristic registrations."""
from __future__ import annotations

from pathlib import Path

from .component_base import base_comp
from .component_ext import ext_comp
from .component_registry import REGISTRY as COMP_REGISTRY
from .extensions_registry import _extensions_installed
from .heuristic_step import ComponentCondition, HeuristicStep
from .heuristic_step_registry import HEURISTIC_STEP_REGISTRY
from .role import DEPLOYER

_T_UI = Path(__file__).parent / "templates" / "deployer" / "ui-deployment"
_UI_SERVICES = ("docs-server", "kg-graph-viewer", "markdown-browser")


def _deploy_catalog_needs_configuration() -> bool:
    catalog = Path(".") / "catalog.yaml"
    if not catalog.exists():
        return False
    template = COMP_REGISTRY.get("catalog").trivial_catalog_content()
    if template is None:
        return False
    return catalog.read_text() == template


def _deploy_env_is_default() -> bool:
    env_file = Path(".") / "deployment.env"
    template = _T_UI / "deployment.env"
    if not env_file.exists() or not template.exists():
        return False
    return env_file.read_text() == template.read_text()


def _deploy_config_is_default() -> bool:
    return _deploy_catalog_needs_configuration() or _deploy_env_is_default()


def _deploy_containers_running() -> bool:
    from .component_ext_command_docker import DOCKER_COMMAND
    name = Path(".").resolve().name.lower()
    return all(DOCKER_COMMAND.is_running(f"jejune-{name}-{svc}-1")[0] for svc in _UI_SERVICES)


def _deploy_images_missing() -> bool:
    return not COMP_REGISTRY.get("deployment").is_available()


def _deploy_services_available() -> bool:
    return _extensions_installed() and all(
        ok for _, ok, _ in COMP_REGISTRY.get("deployment").check_ui_services()
    )


def _deploy_catalog_check_fails() -> bool:
    try:
        from jejune_catalog._impl import _check_deployment_impl
        cwd = Path.cwd()
        full_cat = cwd.parent.parent / "jejune_catalog" / "full-catalog.yaml"
        results = _check_deployment_impl(cwd, full_cat)
        return any(not ok for _, ok, _ in results)
    except Exception:
        return False


def _docs_server_url() -> str:
    port = "8765"
    env_file = Path(".") / "deployment.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("DOCS_SERVER_PORT="):
                port = line.split("=", 1)[1].strip()
                break
    return f"http://localhost:{port}"


def _is_catalog_installed() -> bool:
    try:
        from jejune_catalog._commands import _load_catalog_docs
    except ImportError:
        return True  # catalog plugin absent — nothing to install
    try:
        docs = _load_catalog_docs(None)
    except Exception:
        return True  # no catalog.yaml → nothing to install
    try:
        eco = COMP_REGISTRY.get("ecosystem")
        eco_root, eco_tmp = eco.resolve_dirs()
        return all(
            eco.repo_status(doc["name"], eco_root, eco_tmp)[0] in ("root", "tmp")
            for doc in docs
        )
    except Exception:
        return False


def _is_deployment_installed() -> bool:
    return _is_catalog_installed() and _extensions_installed()


def register_heuristics() -> None:
    HEURISTIC_STEP_REGISTRY.register_precondition("deployer extensions installed",   _extensions_installed)
    HEURISTIC_STEP_REGISTRY.register_precondition("deployer role detected",          DEPLOYER.is_deployer)
    HEURISTIC_STEP_REGISTRY.register_precondition("deployment config is default",    _deploy_config_is_default)
    HEURISTIC_STEP_REGISTRY.register_precondition("deployment images missing",       _deploy_images_missing)
    HEURISTIC_STEP_REGISTRY.register_precondition("deployment containers running",   _deploy_containers_running)
    HEURISTIC_STEP_REGISTRY.register_precondition("deployment services available",   _deploy_services_available)
    HEURISTIC_STEP_REGISTRY.register_precondition("deployment installed",            _is_deployment_installed)

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Install deployment",
        command="jejune deployment install",
        conditions=[DEPLOYER.is_deployer],
        anti_conditions=[_is_deployment_installed],
    ), roles={"deployer"})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Install docker desktop",
        command=COMP_REGISTRY.get("docker-command").hint, order=2,
        conditions=[DEPLOYER.is_deployer],
        anti_conditions=[ComponentCondition("docker-command")],
    ), roles={"deployer"})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Wrap up configuration",
        command="edit config files", order=5,
        conditions=[DEPLOYER.is_deployer, _deploy_config_is_default],
        anti_conditions=[],
    ), roles={"deployer"})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Fix deployment catalog", command="jejune catalog check", order=6,
        conditions=[DEPLOYER.is_deployer, _deploy_catalog_check_fails],
        anti_conditions=[_deploy_catalog_needs_configuration],
    ), roles={"deployer"})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Build deployment", command="jejune build", order=10,
        conditions=[DEPLOYER.is_deployer, ComponentCondition("docker-command"), _deploy_images_missing, _is_deployment_installed],
        anti_conditions=[_deploy_catalog_check_fails],
    ), roles={"deployer"})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Start deployment", command="jejune up", order=20,
        conditions=[DEPLOYER.is_deployer, ComponentCondition("docker-command")],
        anti_conditions=[_deploy_images_missing, _deploy_containers_running],
    ), roles={"deployer"})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Install deployer CLI extensions",
        command="jejune extensions install", order=22,
        conditions=[DEPLOYER.is_deployer, ComponentCondition("extensions"), _deploy_containers_running],
        anti_conditions=[_extensions_installed],
    ), roles={"deployer"})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Check deployment status", command="jejune deployment status", order=25,
        conditions=[DEPLOYER.is_deployer, ComponentCondition("extensions"), _deploy_containers_running, _extensions_installed],
        anti_conditions=[_deploy_services_available],
    ), roles={"deployer"})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Browse docs server",
        command=lambda: f"web-browse UI at {_docs_server_url()}", order=30,
        conditions=[DEPLOYER.is_deployer, _deploy_containers_running, _deploy_services_available],
        anti_conditions=[],
    ), roles={"deployer"})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Deployment running stop", command="jejune down", order=35,
        conditions=[DEPLOYER.is_deployer, ComponentCondition("docker-command"), _deploy_containers_running],
        anti_conditions=[],
    ), roles={"deployer"})

    dep_fix_pairs: list[tuple[base_comp, str]] = [
        (inst, inst.hint)
        for inst in COMP_REGISTRY
        if isinstance(inst, ext_comp) and inst.hint
    ]
    existing = frozenset({"docker-command", "extensions"})
    for dep_inst, label in dep_fix_pairs:
        if dep_inst.name in existing:
            continue
        HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
            label=label,
            command=label,
            conditions=[DEPLOYER.is_deployer],
            anti_conditions=[ComponentCondition(dep_inst.name)],
        ), roles={"deployer"})

    dep_topo = COMP_REGISTRY.sorted_subset([inst for inst, _ in dep_fix_pairs])
    n = len(dep_topo)
    HEURISTIC_STEP_REGISTRY.register_role_ordering("deployer", {
        label: (dep_topo.index(inst) - n) * 10
        for inst, label in dep_fix_pairs
    } | {"Install deployment": -2, "Wrap up configuration": -1})
