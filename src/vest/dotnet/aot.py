from typing import Literal

from vest.common.collections import maybe
from vest.spec.core import run

def ilc_compile(
    *,
    input: str,
    output: str,
    references: list[str] = [],
    target_arch: str,
    target_os: str = "linux",
    stdlib_assembly: str | None = None,
    method_body_fold = False,
    optimization: Literal["disable", "enable", "favor_size", "favor_time"] = "disable",
    emit_debug_info = True,
    codegen_options: list[str] = [],
    pre_init_statics = True,
    generate_reflection_data = False,
    direct_pinvoke: list[str] = [],
    nativelib = False,
    disable_il_scanner = False
):
    """
    Compiles an IL assembly into a native object file via `dotnet ilc`.

    @input: The IL assembly to compile.
    @output: The path to write the compiled object file to.
    @references: The assemblies that `@input` references.
    @target_arch: Specifies the architecture to compile for, e.g. `x64` or `arm64`.
    @target_os: Specifies the ABI and binary format to compile for, e.g. `linux` or `windows`.
    @stdlib_assembly: The name of the assembly to consider the standard library.
    @method_body_fold: If `"true`", identical method bodies will be merged (folded).
    @optimization: Controls program optimization.
    @emit_debug_info: If `"true"`, debug information will be included in the object file.
    @codegen_options: Code generation options in the form of `<key>=<value>`. See https://github.com/dotnet/runtime/blob/main/src/coreclr/jit/jitconfigvalues.h#L32 for details.
    @pre_init_statics: If `"true"`, static fields will be evaluated at compile-time (if possible).
    @generate_reflection_data: If `"true"`, reflection data will be included with the object file.
    @direct_pinvoke: A list of libraries to call the functions of directly, without a P/Invoke stub/wrapper. 
    @nativelib: If `"true"`, the IL should be compiled as a static or shared library.
    """

    args = [
        "ilc",
        input,
        f"-o:{output}",
        *[f"-r:{x}" for x in references],
        f"--targetos:{target_os}", # This option only chooses the ABI and binary format - for 'linux', the pair is System V and ELF.
        f"--targetarch:{target_arch}",
        *maybe("--debug", emit_debug_info == "true"),
        *maybe(f"--systemmodule:{stdlib_assembly}", stdlib_assembly is not None),
        *maybe("--preinitstatics", pre_init_statics == "true"),
        *maybe("--methodbodyfolding", method_body_fold == "true"),
        *maybe("--nativelib", nativelib == "true"),
        *maybe("--noscan", disable_il_scanner == "true"),
        *[f"--directpinvoke:{x}" for x in direct_pinvoke],
        f"--reflectiondata:{'all' if generate_reflection_data == 'true' else 'none'}",
        "--verbose",
        "--noscan"
    ]

    if optimization != "disable":
        match optimization:
            case "enable":
                args.append("--optimize")
            case "favor_size":
                args.append("--optimize-space")
            case "favor_time":
                args.append("--optimize-time")

    for opt in codegen_options:
        args.extend(["--codegenopt", opt])

    run("dotnet", args)
