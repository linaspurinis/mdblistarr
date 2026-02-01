from django import template
from pathlib import Path

register = template.Library()

VERSION_PATH = Path(__file__).resolve().parents[2] / "version"

@register.simple_tag
def version():
    try:
        content = VERSION_PATH.read_text(encoding="utf-8")
    except OSError:
        return "unknown"

    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped

    return "unknown"
