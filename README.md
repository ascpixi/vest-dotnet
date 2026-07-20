# Vest support for .NET
[![image](https://img.shields.io/pypi/v/vest-build-dotnet.svg)](https://pypi.python.org/pypi/vest-build-dotnet)
[![image](https://img.shields.io/pypi/l/vest-build-dotnet.svg)](https://github.com/ascpixi/vest-dotnet/blob/master/LICENSE)
[![image](https://img.shields.io/pypi/pyversions/vest-build-dotnet.svg)](https://pypi.python.org/pypi/vest-build-dotnet)
[![Actions status](https://github.com/ascpixi/vest-dotnet/workflows/CI/badge.svg)](https://github.com/ascpixi/vest-dotnet/actions)

.NET build support for [Vest](https://pypi.org/project/vest-build/), a Python-based build
system for bespoke use.

## Requirements
The project assumes that the following dependencies are installed:

- The [.NET SDK](https://dotnet.microsoft.com/download), with `dotnet` on `PATH`.
- `csc`. You can install this via `dotnet tool install csc`.
- `ilc` for Native AOT compilation. You can install this via `dotnet tool install ilc`.

## Examples

### Building or publishing an existing project

```python
from vest import *
from vest.dotnet import dotnet_publish

component(name = "my-service")

@task
def publish():
    artifacts = dotnet_publish(
        configuration = "Release",
        rid = "linux-x64"
    )

    return artifacts.publish
```

### Native AOT compilation

`ilc_compile` turns an IL assembly into a native object file via `dotnet ilc`, which can then
be fed into your own linker invocation:

```python
from vest.dotnet import ilc_compile

@task
def aot():
    asm = dotnet_build(
        configuration = dotnet_configuration(),
        rid = rid(),
        properties = {
            "Arch": "x64"
        }
    )

    ilc_compile(
        input = asm.build,
        output = f"{artifact_dir()}/obj/my-object.o",
        target_arch = "x64",
        stdlib_assembly = "Azerou.CoreLib",
        nativelib = True
    )
```
