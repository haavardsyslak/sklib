import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class SmokeTestError(RuntimeError):
    """Raised when the installed-package smoke test cannot be prepared."""


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Exercise an installed SKLib wheel in a fresh consumer workspace"
    )
    parser.add_argument(
        "--wheel",
        type=Path,
        help="Wheel to install; defaults to the single dist/sklib-*.whl file",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Keep generated workspace at this path instead of using a temporary one",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    repository = Path(__file__).resolve().parent.parent
    wheel = _select_wheel(repository, args.wheel)

    if args.workspace is None:
        with tempfile.TemporaryDirectory(prefix="sklib-consumer-") as temporary:
            _exercise_workspace(wheel, Path(temporary) / "library")
        return 0

    workspace = args.workspace.expanduser().resolve()
    if workspace.exists():
        if any(workspace.iterdir()):
            raise SmokeTestError(f"Workspace is not empty: {workspace}")
        workspace.rmdir()
    _exercise_workspace(wheel, workspace)
    print(f"Consumer workspace kept at: {workspace}")
    return 0


def _select_wheel(repository: Path, configured: Path | None) -> Path:
    if configured is not None:
        wheel = configured.expanduser().resolve()
        if not wheel.is_file():
            raise SmokeTestError(f"Wheel not found: {wheel}")
        return wheel

    wheels = sorted((repository / "dist").glob("sklib-*.whl"))
    if len(wheels) != 1:
        raise SmokeTestError(
            "Expected one dist/sklib-*.whl file; run 'uv build' or pass --wheel"
        )
    return wheels[0].resolve()


def _exercise_workspace(wheel: Path, workspace: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise SmokeTestError("uv was not found in PATH")

    _run([uv, "tool", "run", "--from", str(wheel), "sklib", "init", str(workspace)])
    pyproject = workspace / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8")
    dependency = f'"sklib @ {wheel.as_uri()}"'
    content = content.replace('"sklib>=0.3,<0.4"', dependency)
    pyproject.write_text(content, encoding="utf-8", newline="\n")

    _run([uv, "sync", "--project", str(workspace)])
    _run_workspace(uv, workspace, "doctor")
    _run_workspace(uv, workspace, "check")
    _run_workspace(uv, workspace, "build")

    if not (workspace / "generated/sklib.db").is_file():
        raise SmokeTestError("Fresh workspace did not produce generated/sklib.db")
    print(f"Installed-wheel consumer smoke test OK: {workspace}")


def _run_workspace(uv: str, workspace: Path, *arguments: str) -> None:
    _run(
        [
            uv,
            "run",
            "--project",
            str(workspace),
            "sklib",
            "--workspace",
            str(workspace),
            *arguments,
        ]
    )


def _run(command: list[str]) -> None:
    environment = os.environ.copy()
    environment.pop("VIRTUAL_ENV", None)
    try:
        subprocess.run(command, check=True, env=environment)
    except subprocess.CalledProcessError as error:
        raise SmokeTestError(
            f"Smoke-test command failed with status {error.returncode}: "
            f"{' '.join(command)}"
        ) from error


if __name__ == "__main__":
    raise SystemExit(main())
