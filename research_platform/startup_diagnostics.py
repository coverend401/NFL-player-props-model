"""Authenticated, opt-in hosted release diagnostics; never bypasses admission."""

import importlib.metadata
import json
import os
import platform
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]


def git_value(args):
    try:
        return subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=3,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def deployment():
    commit = git_value(["rev-parse", "HEAD"])
    branch = git_value(["symbolic-ref", "--short", "HEAD"])
    origin = git_value(["config", "--get", "remote.origin.url"])
    expected_repo = "coverend401/NFL-player-props-model"
    try:
        remote = urlsplit(origin)
        repository_matches = (
            remote.hostname == "github.com"
            and remote.path.strip("/").removesuffix(".git") == expected_repo
        ) or origin.removesuffix(".git") == "git@github.com:" + expected_repo
    except ValueError:
        repository_matches = False
    return {
        "diagnostics_version": "hosted-release-preflight-r1",
        "commit": commit if re.fullmatch(r"[a-f0-9]{40}", commit) else "unavailable",
        "branch": branch
        if re.fullmatch(r"[A-Za-z0-9._/-]{1,120}", branch)
        else "unavailable",
        "python": platform.python_version(),
        "repository": expected_repo
        if repository_matches
        else "unverified or different repository",
        "expected_branch": "sportsgameodds-free-feasibility",
        "expected_entrypoint": "odds_value_research.py",
        "expected_release": "research-week11-frozen-20261120-r2",
        "research_pointer_override_configured": bool(
            os.environ.get("NFL_RESEARCH_INFERENCE_POINTER")
        ),
    }


def safe_failure(error):
    """Never return raw exception text, paths, environment values or tracebacks."""
    text = str(error)
    if text.startswith("Runtime package mismatch:"):
        package = text.split(":", 2)[1].strip()
        pins = dict(
            line.strip().split("==")
            for line in (ROOT / "requirements-production.lock").read_text().splitlines()
            if "==" in line and not line.startswith("#")
        )
        if package in pins:
            try:
                installed = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                installed = "not installed"
            return {
                "code": "RUNTIME_PACKAGE_MISMATCH",
                "package": package,
                "expected": pins[package],
                "installed": installed
                if re.fullmatch(r"[0-9][0-9A-Za-z.+-]{0,40}", installed)
                else "unrecognised version",
            }
    known = {
        "Release requires Python": "PYTHON_RUNTIME_MISMATCH",
        "Requested research inference pointer missing": "RESEARCH_POINTER_MISSING",
        "Inference pointer/manifest mismatch": "RESEARCH_POINTER_HASH_MISMATCH",
        "Inference source/code mismatch": "RESEARCH_SOURCE_HASH_MISMATCH",
        "Release/code mismatch:": "PARENT_SOURCE_HASH_MISMATCH",
        "Inference integrity mismatch:": "RESEARCH_FILE_HASH_MISMATCH",
        "Release integrity mismatch:": "PARENT_FILE_HASH_MISMATCH",
        "Incomplete or unexpected inference artifact set": "RESEARCH_ARTIFACT_SET_MISMATCH",
        "Missing or unexpected release data files": "PARENT_ARTIFACT_SET_MISMATCH",
        "Inference runtime mismatch": "RESEARCH_RUNTIME_MISMATCH",
        "Release/runtime mismatch": "PARENT_RUNTIME_MISMATCH",
        "Release paths must be relative": "INVALID_POINTER_PATH",
        "Release path escapes repository": "INVALID_POINTER_PATH",
    }
    if isinstance(error, FileNotFoundError):
        return {"code": "REQUIRED_RELEASE_FILE_MISSING"}
    for prefix, code in known.items():
        if text.startswith(prefix):
            return {"code": code}
    if isinstance(error, json.JSONDecodeError):
        return {"code": "RELEASE_JSON_INVALID"}
    return {
        "code": "RELEASE_VALIDATION_REJECTED",
        "exception_type": type(error).__name__,
    }


def preflight():
    from .inference_release import resolve_research_release

    try:
        directory, manifest = resolve_research_release(ROOT)
        if (
            not manifest
            or manifest.get("release_id") != "research-week11-frozen-20261120-r2"
        ):
            return {"status": "FAIL", "code": "WRONG_RESEARCH_RELEASE"}
        import pandas as pd

        slate = pd.read_parquet(directory / "slate.parquet")
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {"status": "FAIL", **safe_failure(error)}
    return {
        "status": "PASS",
        "release": manifest["release_id"],
        "base_forecast_rows": len(slate),
    }


def render():
    with st.expander("Authenticated deployment diagnostics", expanded=False):
        st.caption(
            "No credentials are shown. This checks the actual hosted checkout and runtime; it makes no provider requests or release changes."
        )
        st.json(deployment())
        if st.button(
            "Check approved release loading", key="research_startup_preflight"
        ):
            result = preflight()
            st.json(result)
            if result["status"] == "FAIL":
                st.error(
                    "Release remains blocked. Share this diagnostic code and deployment metadata, not secrets."
                )
