"""Deployer-role heuristic registrations."""
from __future__ import annotations

from pathlib import Path

from .component_ext import ext_comp
from .component_registry import REGISTRY as COMP_REGISTRY
from .plugin_package_catalog import PLUGIN_PACKAGE_CATALOG
from .heuristic_step import ComponentCondition, HeuristicStep
from .heuristic_step_registry import HEURISTIC_STEP_REGISTRY
from .role import DEPLOYER

_T_UI = Path(__file__).parent / "templates" / "deployer" / "ui-deployment"


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
    return all(
        DOCKER_COMMAND.is_running(f"jejune-{name}-{svc}-1")[0]
        for svc in COMP_REGISTRY.get("deployment").service_names
    )


def _deploy_images_missing() -> bool:
    return not COMP_REGISTRY.get("deployment").is_available()


def _deploy_services_available() -> bool:
    return PLUGIN_PACKAGE_CATALOG.packages_installed() and all(
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


def register_heuristics() -> None:
    HEURISTIC_STEP_REGISTRY.register_precondition("deployer plugin-packages installed",   PLUGIN_PACKAGE_CATALOG.packages_installed)
    HEURISTIC_STEP_REGISTRY.register_precondition("deployer role detected",          DEPLOYER.is_deployer)
    HEURISTIC_STEP_REGISTRY.register_precondition("deployment config is default",    _deploy_config_is_default)
    HEURISTIC_STEP_REGISTRY.register_precondition("deployment images missing",       _deploy_images_missing)
    HEURISTIC_STEP_REGISTRY.register_precondition("deployment containers running",   _deploy_containers_running)
    HEURISTIC_STEP_REGISTRY.register_precondition("deployment services available",   _deploy_services_available)

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Install docker desktop",
        command=COMP_REGISTRY.get("docker-command").hint, order=2,
        conditions=[DEPLOYER.is_deployer],
        anti_conditions=[ComponentCondition("docker-command")],
    ), roles={"deployer"})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Install plugin packages",
        command="jejune plugin-packages install", order=3,
        conditions=[DEPLOYER.is_deployer],
        anti_conditions=[ComponentCondition("plugin-packages")],
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
        conditions=[DEPLOYER.is_deployer, ComponentCondition("docker-command"), _deploy_images_missing, PLUGIN_PACKAGE_CATALOG.packages_installed],
        anti_conditions=[_deploy_catalog_check_fails],
    ), roles={"deployer"})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Start deployment", command="jejune up", order=20,
        conditions=[DEPLOYER.is_deployer, ComponentCondition("docker-command")],
        anti_conditions=[_deploy_images_missing, _deploy_containers_running],
    ), roles={"deployer"})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Install deployer plugin packages",
        command="jejune plugin-packages install", order=22,
        conditions=[DEPLOYER.is_deployer, ComponentCondition("plugin-packages"), _deploy_containers_running],
        anti_conditions=[PLUGIN_PACKAGE_CATALOG.packages_installed],
    ), roles={"deployer"})

    HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
        label="Check deployment status", command="jejune deployment status", order=25,
        conditions=[DEPLOYER.is_deployer, ComponentCondition("plugin-packages"), _deploy_containers_running, PLUGIN_PACKAGE_CATALOG.packages_installed],
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

    # One fix step per ext_comp: if unavailable, show its hint as the action.
    # docker-command and plugin-packages already have explicit steps.
    _skip = frozenset({"docker-command", "plugin-packages"})
    for inst in COMP_REGISTRY:
        if not isinstance(inst, ext_comp) or not inst.hint or inst.name in _skip:
            continue
        HEURISTIC_STEP_REGISTRY.register(HeuristicStep(
            label=inst.hint,
            command=inst.hint,
            conditions=[DEPLOYER.is_deployer],
            anti_conditions=[ComponentCondition(inst.name)],
        ), roles={"deployer"})

    # Order ext_comp fix steps by topological dep order so prerequisites appear
    # first.
    _ext_deps = COMP_REGISTRY.sorted_subset([
        inst for inst in COMP_REGISTRY
        if isinstance(inst, ext_comp) and inst.hint and inst.name not in _skip
    ])
    HEURISTIC_STEP_REGISTRY.register_role_ordering("deployer", {
        inst.hint: (i - len(_ext_deps)) * 10
        for i, inst in enumerate(_ext_deps)
    } | {"Install plugin packages": -2, "Wrap up configuration": -1})
