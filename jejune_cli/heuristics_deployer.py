"""Deployer-role heuristic registrations."""
from __future__ import annotations

from pathlib import Path

from .component_ext import ext_comp
from .component_registry import ComponentRegistry
from .heuristic_step import ComponentCondition, HeuristicStep
from .heuristic_step_registry import HeuristicStepRegistry
from .role import Role

_T_UI = Path(__file__).parent / "templates" / "deployer" / "ui-deployment"


def register_heuristics(
    registry: HeuristicStepRegistry,
    component_registry: ComponentRegistry,
) -> None:
    def _deploy_catalog_needs_configuration() -> bool:
        catalog_comp = component_registry.get("catalog")
        local_catalog = Path(".") / "catalog.yaml"
        if not local_catalog.exists():
            return False
        template = catalog_comp.trivial_catalog_content()
        if template is None:
            return False
        return local_catalog.read_text() == template

    def _deploy_env_is_default() -> bool:
        env_file = Path(".") / "deployment.env"
        template = _T_UI / "deployment.env"
        if not env_file.exists() or not template.exists():
            return False
        return env_file.read_text() == template.read_text()

    def _deploy_config_is_default() -> bool:
        return _deploy_catalog_needs_configuration() or _deploy_env_is_default()

    def _deploy_containers_running() -> bool:
        name = Path(".").resolve().name.lower()
        deployment = component_registry.get("deployment")
        docker_command = component_registry.get("docker-command")
        return all(
            docker_command.is_running(f"jejune-{name}-{svc}-1")[0]
            for svc in deployment.service_names
        )

    def _deploy_images_missing() -> bool:
        return not component_registry.get("deployment").is_available()

    def _deploy_services_available() -> bool:
        return component_registry.get("plugin-packages").packages_installed() and all(
            ok for _, ok, _ in component_registry.get("deployment").check_ui_services()
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

    registry.register_precondition("deployer plugin-packages installed", component_registry.get("plugin-packages").packages_installed)
    registry.register_precondition("deployer role detected",             Role.is_deployer_cwd)
    registry.register_precondition("deployment config is default",       _deploy_config_is_default)
    registry.register_precondition("deployment images missing",          _deploy_images_missing)
    registry.register_precondition("deployment containers running",      _deploy_containers_running)
    registry.register_precondition("deployment services available",      _deploy_services_available)

    registry.register(HeuristicStep(
        label="Install docker desktop",
        command=component_registry.get("docker-command").hint, order=2,
        conditions=[],
        anti_conditions=[ComponentCondition("docker-command", component_registry)],
    ), roles={"deployer"})

    registry.register(HeuristicStep(
        label="Install plugin packages",
        command="jejune plugin-packages install", order=3,
        conditions=[],
        anti_conditions=[ComponentCondition("plugin-packages", component_registry)],
    ), roles={"deployer"})

    registry.register(HeuristicStep(
        label="Wrap up configuration",
        command="edit config files", order=5,
        conditions=[_deploy_config_is_default],
        anti_conditions=[],
    ), roles={"deployer"})

    registry.register(HeuristicStep(
        label="Fix deployment catalog", command="jejune catalog check", order=6,
        conditions=[_deploy_catalog_check_fails],
        anti_conditions=[_deploy_catalog_needs_configuration],
    ), roles={"deployer"})

    registry.register(HeuristicStep(
        label="Build deployment", command="jejune build", order=10,
        conditions=[ComponentCondition("docker-command", component_registry), _deploy_images_missing, component_registry.get("plugin-packages").packages_installed],
        anti_conditions=[_deploy_catalog_check_fails],
    ), roles={"deployer"})

    registry.register(HeuristicStep(
        label="Start deployment", command="jejune up", order=20,
        conditions=[ComponentCondition("docker-command", component_registry)],
        anti_conditions=[_deploy_images_missing, _deploy_containers_running],
    ), roles={"deployer"})

    registry.register(HeuristicStep(
        label="Install deployer plugin packages",
        command="jejune plugin-packages install", order=22,
        conditions=[ComponentCondition("plugin-packages", component_registry), _deploy_containers_running],
        anti_conditions=[component_registry.get("plugin-packages").packages_installed],
    ), roles={"deployer"})

    registry.register(HeuristicStep(
        label="Check deployment status", command="jejune deployment status", order=25,
        conditions=[ComponentCondition("plugin-packages", component_registry), _deploy_containers_running, component_registry.get("plugin-packages").packages_installed],
        anti_conditions=[_deploy_services_available],
    ), roles={"deployer"})

    registry.register(HeuristicStep(
        label="Browse docs server",
        command=lambda: f"web-browse UI at {_docs_server_url()}", order=30,
        conditions=[_deploy_containers_running, _deploy_services_available],
        anti_conditions=[],
    ), roles={"deployer"})

    registry.register(HeuristicStep(
        label="Deployment running stop", command="jejune down", order=35,
        conditions=[ComponentCondition("docker-command", component_registry), _deploy_containers_running],
        anti_conditions=[],
    ), roles={"deployer"})

    # One fix step per ext_comp: if unavailable, show its hint as the action.
    _skip = frozenset({"docker-command", "plugin-packages"})
    for inst in component_registry:
        if not isinstance(inst, ext_comp) or not inst.hint or inst.name in _skip:
            continue
        registry.register(HeuristicStep(
            label=inst.hint,
            command=inst.hint,
            conditions=[],
            anti_conditions=[ComponentCondition(inst.name, component_registry)],
        ), roles={"deployer"})

    _ext_deps = component_registry.sorted_subset([
        inst for inst in component_registry
        if isinstance(inst, ext_comp) and inst.hint and inst.name not in _skip
    ])
    registry.register_role_ordering("deployer", {
        inst.hint: (i - len(_ext_deps)) * 10
        for i, inst in enumerate(_ext_deps)
    } | {"Install plugin packages": -2, "Wrap up configuration": -1})
