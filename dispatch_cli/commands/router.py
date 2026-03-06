"""Router management commands."""

import json
import os
import signal
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import requests
import toml
import typer
from dispatch_agents.models import TopicMessage

from dispatch_cli.logger import get_logger
from dispatch_cli.utils import LOCAL_ROUTER_PORT, LOCAL_ROUTER_URL

from ..registry import get_agent_from_registry, list_agents_from_registry

router_app = typer.Typer(name="router", help="Multi-agent router management")

DISPATCH_NETWORK = "dispatch-network"
ROUTER_SERVICE_NAME = "dispatch-router"
ROUTER_IMAGE_TAG = "dispatch-router:latest"
DISPATCH_CLI_LABEL = "com.dispatch.cli=true"

# Router tracking directory
ROUTER_TRACKING_DIR = Path.home() / ".dispatch" / "routers"


def get_router_tracking_file(port: int) -> Path:
    """Get the path to the router tracking file for a given port."""
    return ROUTER_TRACKING_DIR / f"{port}.json"


def register_router(port: int, pid: int) -> None:
    """Register a running router in the tracking directory.

    Args:
        port: Port the router is running on
        pid: Process ID of the router
    """
    ROUTER_TRACKING_DIR.mkdir(parents=True, exist_ok=True)
    tracking_file = get_router_tracking_file(port)
    tracking_data = {
        "port": port,
        "pid": pid,
        "started_at": datetime.now(UTC).isoformat(),
    }
    with open(tracking_file, "w") as f:
        json.dump(tracking_data, f, indent=2)


def unregister_router(port: int) -> bool:
    """Remove a router from the tracking directory.

    Args:
        port: Port of the router to unregister

    Returns:
        True if file was removed, False if it didn't exist
    """
    tracking_file = get_router_tracking_file(port)
    if tracking_file.exists():
        tracking_file.unlink()
        return True
    return False


def get_tracked_routers() -> list[dict]:
    """Get all tracked routers.

    Returns:
        List of router info dicts with port, pid, and started_at
    """
    if not ROUTER_TRACKING_DIR.exists():
        return []

    routers = []
    for tracking_file in ROUTER_TRACKING_DIR.glob("*.json"):
        try:
            with open(tracking_file) as f:
                data = json.load(f)
                # Verify process is still running
                pid = data.get("pid")
                if pid:
                    try:
                        os.kill(pid, 0)  # Check if process exists
                        data["running"] = True
                    except OSError:
                        data["running"] = False
                routers.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return sorted(routers, key=lambda r: r.get("port", 0))


def stop_router_by_port(port: int) -> tuple[bool, str]:
    """Stop a router on a specific port.

    Args:
        port: Port of the router to stop

    Returns:
        Tuple of (success, message)
    """
    logger = get_logger()

    # First try graceful shutdown via HTTP
    try:
        response = requests.post(f"{LOCAL_ROUTER_URL}:{port}/shutdown", timeout=2)
        if response.status_code == 200:
            unregister_router(port)
            return True, f"Stopped router on port {port}"
    except requests.exceptions.RequestException as e:
        logger.warning(f"Error stopping router: {e}")
        logger.warning("Router might not be responding, trying PID-based shutdown")
        pass  # Router might not be responding, try PID-based shutdown

    # Try to stop via PID file
    tracking_file = get_router_tracking_file(port)
    if tracking_file.exists():
        try:
            with open(tracking_file) as f:
                data = json.load(f)
                pid = data.get("pid")
                if pid:
                    try:
                        os.killpg(os.getpgid(pid), signal.SIGTERM)
                        unregister_router(port)
                        return True, f"Stopped router on port {port} (PID {pid})"
                    except ProcessLookupError:
                        unregister_router(port)
                        return (
                            True,
                            f"Router on port {port} was already stopped (cleaned up stale tracking file)",
                        )
                    except PermissionError:
                        return False, f"No permission to kill router process {pid}"
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"Error reading tracking file: {e}")

    return False, f"No router found on port {port}"


def stop_all_routers() -> list[tuple[int, bool, str]]:
    """Stop all tracked routers.

    Returns:
        List of (port, success, message) tuples
    """
    results = []
    routers = get_tracked_routers()

    for router in routers:
        port = router.get("port")
        if port:
            success, message = stop_router_by_port(port)
            results.append((port, success, message))

    return results


def get_sdk_path_from_pyproject() -> str | None:
    """Extract SDK path from pyproject.toml if it exists."""
    logger = get_logger()
    cwd = os.getcwd()
    logger.debug(cwd)
    pyproject_path = os.path.join(cwd, "pyproject.toml")

    if not os.path.exists(pyproject_path):
        return None

    try:
        with open(pyproject_path) as f:
            data = toml.load(f)

        # Check for uv.sources first, then fall back to other source definitions
        sources = data.get("tool", {}).get("uv", {}).get("sources", {})
        if "dispatch-agents" in sources and "path" in sources["dispatch-agents"]:
            sdk_path = sources["dispatch-agents"]["path"]
            # Convert relative path to absolute
            return os.path.abspath(os.path.join(cwd, sdk_path))

        # Could add other source formats here if needed
        return None
    except Exception as e:
        logger.warning(f"Could not parse pyproject.toml: {e}")
        return None


@router_app.command("start")
def start_router(
    force_rebuild: Annotated[
        bool,
        typer.Option(
            help="Rebuild the router image and restart the container even if it's already running"
        ),
    ] = False,
    port: Annotated[
        int, typer.Option(help="Port to expose the router on")
    ] = LOCAL_ROUTER_PORT,
    containerized: Annotated[
        bool, typer.Option(help="Run the local router as a container")
    ] = False,
):
    """Start the multi-agent router and all registered agents."""
    logger = get_logger()
    if containerized:
        try:
            # 1. Create Docker network
            logger.debug(f"Creating Docker network '{DISPATCH_NETWORK}'...")
            network_result = subprocess.run(
                ["docker", "network", "create", DISPATCH_NETWORK],
                capture_output=True,
                text=True,
            )
            if (
                network_result.returncode != 0
                and "already exists" not in network_result.stderr
            ):
                logger.error(f"Failed to create network: {network_result.stderr}")
                raise typer.Exit(1)
            elif "already exists" in network_result.stderr:
                logger.success(f"Network '{DISPATCH_NETWORK}' already exists")
            else:
                logger.success(f"Created network '{DISPATCH_NETWORK}'")

            # 2. Build and start router service
            if force_rebuild:
                logger.debug("Forcing router rebuild...")
            else:
                logger.debug("Starting router service...")

            # Build router image with SSH agent forwarding from parent directory to include dispatch_cli
            cli_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

            # Check if local SDK is explicitly configured in pyproject.toml
            sdk_root = get_sdk_path_from_pyproject()

            if sdk_root and os.path.exists(sdk_root):
                logger.success(f"Using local SDK from pyproject.toml: {sdk_root}")
            else:
                logger.debug("Using git installation (default)")
                sdk_root = None

            # Choose Dockerfile and build args based on SDK availability
            router_dir = os.path.dirname(os.path.dirname(__file__)) + "/router"

            if sdk_root:
                # Use local Dockerfile with build context
                router_dockerfile = router_dir + "/Dockerfile.local"
                build_cmd = [
                    "docker",
                    "build",
                    "--build-context",
                    f"sdk={sdk_root}",
                ]
            else:
                # Use git Dockerfile with SSH
                router_dockerfile = router_dir + "/Dockerfile"
                build_cmd = [
                    "docker",
                    "build",
                    "--ssh",
                    "default",
                ]
            if force_rebuild:
                build_cmd.extend(["--pull", "--no-cache"])
            build_cmd.extend(
                [
                    "-f",
                    router_dockerfile,
                    "-t",
                    ROUTER_IMAGE_TAG,
                    cli_root,
                ]
            )

            build_result = subprocess.run(build_cmd, capture_output=True, text=True)
            if build_result.returncode != 0:
                logger.error(f"Failed to build router image: {build_result.stderr}")
                raise typer.Exit(1)
            logger.success(f"Built router image: {ROUTER_IMAGE_TAG}")

            # Stop existing router if running
            subprocess.run(
                ["docker", "stop", ROUTER_SERVICE_NAME], capture_output=True, text=True
            )
            subprocess.run(
                ["docker", "rm", ROUTER_SERVICE_NAME], capture_output=True, text=True
            )

            # Start router container
            router_cmd = [
                "docker",
                "run",
                "-d",
                "--name",
                ROUTER_SERVICE_NAME,
                "--label",
                DISPATCH_CLI_LABEL,
                "--network",
                DISPATCH_NETWORK,
                "--network-alias",
                "dispatch.api",  # Make accessible at dispatch.api for consistency with production
                "-p",
                f"{port}:8080",  # Expose router to host
                "-v",
                f"{os.path.expanduser('~')}/.dispatch_agents:/root/.dispatch_agents",  # Mount registry
                ROUTER_IMAGE_TAG,
            ]
            router_result = subprocess.run(router_cmd, capture_output=True, text=True)
            if router_result.returncode == 0:
                container_id = router_result.stdout.strip()
                logger.success(f"Started router service ({ROUTER_SERVICE_NAME})")
                logger.info(f"    Container ID: {container_id[:12]}...")
                logger.info(f"    Router URL: {LOCAL_ROUTER_URL}:{port}")
            else:
                logger.error(f"Failed to start router: {router_result.stderr}")
                raise typer.Exit(1)
        except Exception as e:
            logger.error(f"Failed to start router: {e}")
            raise typer.Exit(1)
        logger.success("Router service starting")
        logger.info("Next steps:")
        logger.info(f"  • View local dashboard: {LOCAL_ROUTER_URL}:{port}")
        return
    else:  # non-containerized mode
        router_service_py = (
            os.path.dirname(os.path.dirname(__file__)) + "/router/service.py"
        )
        router_cmd = [
            sys.executable,
            router_service_py,
            str(port),
        ]
        logger.success(f"Router service starting on port {port}")
        logger.info("Next steps:")
        logger.info(f"  • View local dashboard: {LOCAL_ROUTER_URL}:{port}")
        subprocess.run(router_cmd, capture_output=False, text=True)
    return


@router_app.command("stop")
def stop_router(
    port: Annotated[
        int, typer.Option(help="Port to stop the router on")
    ] = LOCAL_ROUTER_PORT,
    all_routers: Annotated[
        bool, typer.Option("--all", help="Stop all tracked routers")
    ] = False,
):
    """Stop router service(s) and all dispatch-cli containers.

    Use --all to stop all tracked routers, or --port to stop a specific one.
    """
    logger = get_logger()
    try:
        if all_routers:
            # Stop all tracked routers
            results = stop_all_routers()
            if not results:
                logger.info("No tracked routers found")
            else:
                for r_port, success, message in results:
                    if success:
                        logger.success(message)
                    else:
                        logger.warning(message)
                stopped = sum(1 for _, success, _ in results if success)
                logger.success(f"Stopped {stopped}/{len(results)} router(s)")
        else:
            # Stop specific router
            success, message = stop_router_by_port(port)
            if success:
                logger.success(message)
            else:
                logger.warning(message)
                raise typer.Exit(1)

        # if docker daemon is not running, exit
        if (
            subprocess.run(["docker", "ps"], capture_output=True, text=True).returncode
            != 0
        ):
            return

        # Find all containers with dispatch-cli label
        logger.debug("Finding all dispatch-cli containers...")
        list_result = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"label={DISPATCH_CLI_LABEL}",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
        )

        if list_result.returncode != 0:
            logger.error(f"Failed to list containers: {list_result.stderr}")
            raise typer.Exit(1)

        container_names = [
            name.strip()
            for name in list_result.stdout.strip().split("\n")
            if name.strip()
        ]

        if not container_names:
            return

        logger.debug(f"Found {len(container_names)} dispatch-cli container(s)")

        # Stop and remove all containers
        stopped_count = 0
        for container_name in container_names:
            stop_result = subprocess.run(
                ["docker", "stop", container_name],
                capture_output=True,
                text=True,
            )

            if stop_result.returncode == 0:
                logger.success(f"Stopped container: {container_name}")
                stopped_count += 1
            else:
                logger.warning(f"Could not stop {container_name}: {stop_result.stderr}")

            # Remove the container
            subprocess.run(
                ["docker", "rm", container_name],
                capture_output=True,
                text=True,
            )

        logger.success(
            f"Stopped and removed {stopped_count}/{len(container_names)} dispatch-cli container(s)"
        )

    except Exception as e:
        logger.error(f"Failed to stop: {e}")
        raise typer.Exit(1)


@router_app.command("list")
def list_routers():
    """List all tracked local routers."""
    logger = get_logger()
    routers = get_tracked_routers()

    if not routers:
        logger.info("No tracked routers found")
        logger.info("Start a router with: dispatch router start")
        return

    logger.info(f"Found {len(routers)} tracked router(s):")
    for router in routers:
        port = router.get("port", "?")
        pid = router.get("pid", "?")
        started_at = router.get("started_at", "?")
        running = router.get("running", False)
        status = "running" if running else "stopped"
        status_icon = "✓" if running else "✗"

        logger.info(f"  {status_icon} Port {port} (PID {pid}) - {status}")
        logger.info(f"      Started: {started_at}")

    # Clean up stale entries
    stale_count = sum(1 for r in routers if not r.get("running", False))
    if stale_count > 0:
        logger.warning(
            f"\n{stale_count} stale entry(ies) found. Run 'dispatch router stop --all' to clean up."
        )


# @router_app.command("status")
def router_status(
    port: Annotated[
        int, typer.Option(help="Port to check the router on")
    ] = LOCAL_ROUTER_PORT,
):
    """Show router and agent container status."""
    logger = get_logger()
    try:
        # Check Docker network
        network_result = subprocess.run(
            ["docker", "network", "inspect", DISPATCH_NETWORK],
            capture_output=True,
            text=True,
        )

        if network_result.returncode == 0:
            logger.success(f"Network '{DISPATCH_NETWORK}' exists")
            network_info = json.loads(network_result.stdout)[0]
            containers = network_info.get("Containers", {})
            logger.info(f"  Connected containers: {len(containers)}")
        else:
            logger.error(f"Network '{DISPATCH_NETWORK}' not found")
            logger.info("Run 'dispatch router start' to create the network")

        # Check router service status
        logger.info("\nRouter Service:")
        router_inspect_result = subprocess.run(
            ["docker", "inspect", ROUTER_SERVICE_NAME, "--format", "{{.State.Status}}"],
            capture_output=True,
            text=True,
        )

        if router_inspect_result.returncode == 0:
            status = router_inspect_result.stdout.strip()
            if status == "running":
                logger.info(f"  {ROUTER_SERVICE_NAME} - {status}")
                logger.info(f"      API URL: {LOCAL_ROUTER_URL}:{port}")
                logger.info(f"      Docs: {LOCAL_ROUTER_URL}:{port}/docs")
            else:
                logger.warning(f"  {ROUTER_SERVICE_NAME} - {status}")
        else:
            logger.warning(f"  {ROUTER_SERVICE_NAME} - not found")
            logger.info("  Run 'dispatch router start' to start the router service")

        # Check registered agents and their container status
        agents = list_agents_from_registry()
        if not agents:
            logger.warning("No agents registered")
            return

        logger.info(f"\nAgent Container Status ({len(agents)} registered):")

        running_count = 0
        for agent in agents:
            # Check if container is running
            inspect_result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    agent.name,
                    "--format",
                    "{{.State.Status}}",
                ],
                capture_output=True,
                text=True,
            )

            if inspect_result.returncode == 0:
                status = inspect_result.stdout.strip()
                if status == "running":
                    logger.success(
                        f"  {agent.name} (dispatchagents-{agent.name}) - {status}"
                    )
                    logger.info(f"      URL: {agent.get_network_url()}")
                    running_count += 1
                else:
                    logger.warning(
                        f"  {agent.name} (dispatchagents-{agent.name}) - {status}"
                    )
            else:
                logger.debug(
                    f"  {agent.name} (dispatchagents-{agent.name}) - not found"
                )

        logger.info(f"\nSummary: {running_count}/{len(agents)} agents running")

        if running_count == 0:
            logger.info("\nTo start all agents: dispatch router start")

    except Exception as e:
        logger.error(f"Failed to check router status: {e}")
        raise typer.Exit(1)


@router_app.command("test")
def test_topic(
    topic: Annotated[str, typer.Argument(help="Topic to route to agents")],
    payload: Annotated[str, typer.Option(help="JSON payload")] = "{}",
    agent: Annotated[
        str | None,
        typer.Option(help="Optional: Test specific agent instead of routing"),
    ] = None,
    timeout: Annotated[int, typer.Option(help="Request timeout in seconds")] = 30,
    router_port: Annotated[
        int, typer.Option(help="Port to test the router on")
    ] = LOCAL_ROUTER_PORT,
):
    """Test routing a message by topic to all matching agents, or to a specific agent."""
    logger = get_logger()
    try:
        # Parse payload
        try:
            payload_dict = json.loads(payload)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON payload: {e}")
            raise typer.Exit(1)

        if agent:
            # Test specific agent directly (legacy mode)
            agent_obj = get_agent_from_registry(agent)
            if not agent_obj:
                logger.error(f"Agent not found: {agent}")
                raise typer.Exit(1)

            # Check if agent handles this topic
            if agent_obj.handles_topic(topic):
                logger.success(f"Agent '{agent_obj.name}' handles topic '{topic}'")
            else:
                logger.warning(
                    f"Agent '{agent_obj.name}' doesn't handle topic '{topic}'"
                )
                # Extract topics from agent functions
                agent_topics = [
                    trigger.topic
                    for func in agent_obj.functions
                    for trigger in func.triggers
                    if trigger.type == "topic" and trigger.topic
                ]
                logger.info(f"  Agent topics: {', '.join(agent_topics)}")

            logger.info("Testing agent directly (bypassing subscription system)")

            # Create message
            message = TopicMessage.create(
                topic=topic,
                payload=payload_dict,
                # uid=str(uuid.uuid4()),
                trace_id=str(uuid.uuid4()),
                sender_id="cli-test",
                # ts=datetime.now(UTC).isoformat(),
                parent_id=None,  # CLI test events are root events
            )

            logger.info(f"Testing agent '{agent_obj.name}' directly")
            logger.info(f"  Topic: {topic}")
            logger.info(f"  Payload: {json.dumps(payload_dict, indent=2)}")
            logger.info(f"  URL: {agent_obj.get_network_url()}")

            # Send request directly to agent
            try:
                response = requests.post(
                    agent_obj.get_network_url(),
                    headers={"Content-Type": "application/json"},
                    data=message.model_dump_json(),
                    timeout=timeout,
                )
                response.raise_for_status()
                result = response.json()

                logger.success("Response received:")
                logger.info(json.dumps(result, indent=2))

            except requests.exceptions.ConnectionError:
                logger.error("Connection failed - is the agent container running?")
                logger.info("Try:")
                logger.info("  dispatch router status")
                logger.info("  dispatch router start")
                raise typer.Exit(1)
            except requests.exceptions.Timeout:
                logger.error(f"Request timed out after {timeout}s")
                raise typer.Exit(1)
            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error {response.status_code}: {e}")
                if response.text:
                    logger.info(f"Response: {response.text}")
                raise typer.Exit(1)
        else:
            # Route via router service (default mode)

            logger.info("Routing message via router service")
            logger.info(f"  Topic: {topic}")
            logger.info(f"  Payload: {json.dumps(payload_dict, indent=2)}")
            logger.info(f"  Router URL: {LOCAL_ROUTER_URL}:{router_port}")

            # Send request to router service
            event_data = {"payload": payload_dict, "sender_id": "cli-test"}

            try:
                response = requests.post(
                    f"{LOCAL_ROUTER_URL}:{router_port}/api/unstable/events/{topic}",
                    headers={"Content-Type": "application/json"},
                    json=event_data,
                    timeout=timeout,
                )
                response.raise_for_status()
                result = response.json()

                logger.success("Routing result:")
                logger.info(f"  Status: {result.get('status', 'unknown')}")
                logger.info(f"  Message: {result.get('message', 'No message')}")

                routed_to = result.get("routed_to", [])
                if routed_to:
                    logger.info(f"  Routed to {len(routed_to)} agent(s):")
                    for agent_info in routed_to:
                        logger.info(
                            f"    • {agent_info['name']} (topics: {', '.join(agent_info['topics'])})"
                        )

                responses = result.get("responses", {})
                if responses:
                    logger.info("Agent Responses:")
                    for agent_name, agent_response in responses.items():
                        logger.info(f"  {agent_name}:")
                        if (
                            isinstance(agent_response, dict)
                            and "error" in agent_response
                        ):
                            logger.error(f"    Error: {agent_response['error']}")
                        else:
                            logger.info(f"    {json.dumps(agent_response, indent=6)}")

            except requests.exceptions.ConnectionError:
                logger.error("Connection failed - is the router service running?")
                logger.info("Try:")
                logger.info("  dispatch router status")
                logger.info("  dispatch router start")
                raise typer.Exit(1)
            except requests.exceptions.Timeout:
                logger.error(f"Request timed out after {timeout}s")
                raise typer.Exit(1)
            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error {response.status_code}: {e}")
                if response.text:
                    logger.info(f"Response: {response.text}")
                raise typer.Exit(1)

    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise typer.Exit(1)
