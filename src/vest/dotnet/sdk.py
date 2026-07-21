# This file defines .NET-related functions used within the component-based build system.

from dataclasses import dataclass
import json
import os
import re
import subprocess
from typing import Literal, Optional
from packaging import version

from vest.common.collections import maybe, single
from vest.spec.types import Component
from vest.spec.core import host, run, artifact_dir

DotnetVerbosity = Literal["quiet", "minimal", "normal", "detailed", "diagnostic"]

cached_version: Optional[str] = None
cached_sdk_path: Optional[str] = None

def dotnet_version() -> str:
    """Gets the short version string of the current .NET SDK (e.g. 8.0)."""

    global cached_version
    if cached_version is not None:
        return cached_version
    
    full = subprocess.check_output("dotnet --version".split()).decode()
    ver = full[:full.rfind(".")]

    cached_version = ver
    return ver

def dotnet_sdk_path() -> str:
    "Gets the full path to the latest .NET SDK installed on the host system."

    global cached_sdk_path
    if cached_sdk_path is not None:
        return cached_sdk_path
    
    sdks_raw = subprocess.check_output(["dotnet", "--list-sdks"]).decode()

    # sdks[i][0]: version, sdks[i][1]: root path (pointing where the version dir is located, not to the dir itself)
    sdks = [(x.group(1), x.group(2)) for x in re.finditer(r"(.+) \[(.+)\]", sdks_raw)]
    latest_sdk = max(sdks, key = lambda x: version.parse(x[0]))

    path = os.path.join(latest_sdk[1], latest_sdk[0])

    cached_sdk_path = path
    return path

def _dotnet(
    action: Literal["build", "publish"],
    rid: str | None,
    configuration: str,
    *,
    verbosity: DotnetVerbosity = "quiet",
    restore: bool = True,
    properties: dict[str, str] = {}
):
    final_props: list[str] = [
        "-p:VestBuild=true",
        f"-p:Repo={host().repo_dir}",
        f"--artifacts-path", artifact_dir()
    ]

    for (k, v) in host().parameters.items():
        if not k.startswith("--"):
            continue # avoid exposing short-form parameters

        # We need to convert the key into PascalCase, as all MSBuild properties are, by convention, pascal cased.
        k = re.sub(r"([a-z])([A-Z])", r"\1 \2", k) # camelCase
        k = re.sub(r"[-_]+", " ", k) # kebab-case and snake_case
        k = "".join(word.capitalize() for word in k.split())

        final_props.append(f"-p:{k}={v}")

    for (k, v) in properties.items():
        final_props.append(f"-p:{k}={v}")

    run("dotnet", [
        action,
        "-c", configuration,
        *(["-r", rid] if rid else []),
        *([] if restore else ["--no-restore"]),
        "-v", verbosity,
        "-tl:off",
        "--nologo",
        *final_props
    ])

    process = subprocess.run(
        [
            "dotnet",
            "build",
            "-c", configuration,
            *(["-r", rid] if rid else []),
            *final_props,
            "--getTargetResult:" + ",".join([
                "BuiltProjectOutputGroup", # we always want `build` artifacts
                "ResolveAssemblyReferences",
                *maybe("PublishItemsOutputGroup", action == "publish") # `publish` artifacts only available in `publish` builds
            ])
        ],
        capture_output = True,
        text = True,
        check = True
    )

    raw = json.loads(process.stdout)
    assert type(raw) is dict, f".NET's --getTargetResult output was not a dictionary ({raw})"
    return raw

def _find_key_artifact(artifacts: dict, group_name: str):
    items = artifacts["TargetResults"][group_name]["Items"]
    assert type(items) is list, f"TargetResults.{group_name}.Items was not an array; it's a {type(items)} instead ({items})"

    for item in items:
        if "IsKeyOutput" in item and item["IsKeyOutput"]:
            p = item["FullPath"]
            assert type(p) is str
            return p
    
    # If there's nothing marked as IsKeyOutput, just use the first one.
    p = items[0]["FullPath"]
    assert type(p) is str
    return p

def _extract_all_artifacts(artifacts: dict):
    results = artifacts["TargetResults"]
    assert type(results) is dict, f"TargetResults was not a dict; it's a {type(results)} instead ({results})"

    paths: list[str] = []

    for value in results.values():
        assert type(value) is dict, f"An element of TargetResults was not a dict; it's a {type(value)} instead ({value})"

        items = value["Items"]
        assert type(items) is list, f"TargetResults[?].Items was not a list; it's a {type(items)} instead ({items})"

        for item in items:
            p = item["FullPath"]
            assert type(p) is str
            paths.append(p)

    return paths

def _extract_references(artifacts: dict) -> list[str]:
    items = artifacts["TargetResults"]["ResolveAssemblyReferences"]["Items"]
    assert type(items) is list, f"TargetResults.ResolveAssemblyReferences.Items was not an array; it's a {type(items)} instead ({items})"
    return [x["FullPath"] for x in items]

@dataclass
class DotnetPublishArtifacts:
    publish: str
    "The path to the main, key publish artifact. For example, for AOT compilation, this would be the native executable."

    build: str
    "The path to the main, key build artifact. This is usually a binary that hasn't been processed by the publish target."

    all: list[str]
    "Full paths to all other artifacts. This also includes non-key artifacts, like debug information."

    references: list[str]
    "A list of full paths to assemblies that have been referenced by the published project."

def dotnet_publish(
    configuration: str,
    rid: str | None = None,
    *,
    verbosity: DotnetVerbosity = "quiet",
    restore: bool = True,
    properties: dict[str, str] = {}
) -> DotnetPublishArtifacts:
    """
    Publishes a .NET project. All resulting files will be placed in the root of the
    calling component's artifact directory - that is, `/artifacts/<component name>/...`
    if `artifacts_path` is set to `None`.
    
    @artifacts_path: The directory to place all artifacts (`bin` and `obj`) in.
    @verbosity: The verbosity level.
    @configuration: The configuration to publish for. By default, `host().config` is used.
    @rid: The runtime identifier, e.g. `linux-x64`.
    @properties: The properties to forward to the build system. Aggregates into `-p:(key)=(value)`.
    """
    artifacts = _dotnet("publish",
        verbosity = verbosity,
        configuration = configuration,
        rid = rid,
        restore = restore,
        properties = properties
    )

    return DotnetPublishArtifacts(
        publish = _find_key_artifact(artifacts, "PublishItemsOutputGroup"),
        build = _find_key_artifact(artifacts, "BuiltProjectOutputGroup"),
        all = _extract_all_artifacts(artifacts),
        references = _extract_references(artifacts)
    )

@dataclass
class DotnetBuildArtifacts:
    build: str
    "The path to the main, key build artifact."

    all: list[str]
    "Full paths to all other artifacts. This also includes non-key artifacts, like debug information."

    references: list[str]
    "A list of full paths to assemblies that have been referenced by the built project."

def dotnet_build(
    configuration: str,
    rid: str | None = None,
    *,
    verbosity: DotnetVerbosity = "quiet",
    restore: bool = True,
    properties: dict[str, str] = {}
) -> DotnetBuildArtifacts:
    """
    Builds a .NET project. All resulting files will be placed in the root of the
    calling component's artifact directory - that is, `/artifacts/<component name>/...`
    if `artifacts_path` is set to `None`.
    
    @artifacts_path: The directory to place all artifacts (`bin` and `obj`) in.
    @verbosity: The verbosity level.
    @configuration: The configuration to publish for. By default, `host().config` is used.
    @rid: The runtime identifier, e.g. `linux-x64`.
    @properties: The properties to forward to the build system. Aggregates into `-p:(key)=(value)`.
    """
    artifacts = _dotnet("build",
        verbosity = verbosity,
        configuration = configuration,
        rid = rid,
        restore = restore,
        properties = properties
    )

    return DotnetBuildArtifacts(
        build = _find_key_artifact(artifacts, "BuiltProjectOutputGroup"),
        all = _extract_all_artifacts(artifacts),
        references = _extract_references(artifacts)
    )
