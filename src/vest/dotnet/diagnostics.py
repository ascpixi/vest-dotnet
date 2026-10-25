import os
import re
from rich.syntax import Syntax
from rich.text import Text

from vest.spec.types import OutputFormatter

# e.g. "./src/GC.cs(13,18): warning CS0649: Field 'markValue' is never assigned to [./src/Kernel.csproj]"
MSBUILD_DIAGNOSTIC = re.compile(
    r"^(?P<path>.+?)\((?P<line>\d+),(?P<column>\d+)\): (?P<severity>warning|error) (?P<code>\w+): (?P<message>.*?)"
    r"(?: \[[^\]]+\.\w+proj\])?$"
)

GUTTER_STYLE = "bold #7aa2f7"

def msbuild_formatter() -> OutputFormatter:
    """
    Creates an output formatter for MSBuild, which displays diagnostics the way rustc and clang do, underlining the
    offending source code. MSBuild repeats every diagnostic in its closing summary; the repeats are hidden.
    """
    seen: set[str] = set()

    def format(line: str):
        match = MSBUILD_DIAGNOSTIC.match(Text.from_ansi(line).plain)
        if match is None:
            return None

        if line in seen:
            return []

        seen.add(line)
        return _diagnostic(match)

    return format

def _diagnostic(match: re.Match[str]):
    color = "#f7768e" if match["severity"] == "error" else "#e0af68"
    number, column = int(match["line"]), int(match["column"])
    gutter = " " * len(match["line"])

    lines = [
        Text.assemble((f"{match['severity']}[{match['code']}]", f"bold {color}"), (f": {match['message']}", "bold")),
        Text.assemble((f"{gutter}--> ", GUTTER_STYLE), f"{os.path.basename(match['path'])}:{number}:{column}")
    ]

    source = _read_line(match["path"], number)
    if source is not None:
        token = re.match(r"\w+|\S", source[column - 1:])
        lines += [
            Text(f"{gutter} |", GUTTER_STYLE),
            Text.assemble((f"{number} | ", GUTTER_STYLE), _highlight(match["path"], source)),
            Text.assemble((f"{gutter} | ", GUTTER_STYLE), " " * (column - 1), ("^" * len(token[0] if token else " "), f"bold {color}"))
        ]

    return lines

def _read_line(path: str, number: int):
    try:
        with open(path, encoding = "utf-8-sig") as f:
            return next((line.rstrip("\n").expandtabs(4) for (i, line) in enumerate(f, 1) if i == number), None)
    except (OSError, UnicodeDecodeError):
        return None

def _highlight(path: str, code: str):
    text = Syntax(code, Syntax.guess_lexer(path, code), theme = "ansi_dark").highlight(code)
    text.rstrip()
    return text
