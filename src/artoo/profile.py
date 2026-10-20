"""Domain profile loader.

A profile lives in ``demos/<profile>/profile.yaml`` and carries everything that is specific to a
data domain, so the engine in ``src/`` stays domain-agnostic. All keys are optional::

    unit_patterns:            # extra column-name patterns, checked before the generic ones
      - [ "_widgets?$", "widgets", "Count of widgets" ]
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import settings

logger = logging.getLogger(__name__)

UnitPattern = tuple[str, str, str]


@dataclass(frozen=True)
class DomainProfile:
    name: str = ""
    unit_patterns: tuple[UnitPattern, ...] = field(default_factory=tuple)


def _profiles_root() -> Path:
    return Path(settings.profiles_dir)


def load_profile(name: str | None = None, root: Path | None = None) -> DomainProfile:
    """Load ``<root>/<name>/profile.yaml``; return an empty profile if missing or invalid."""
    profile_name = name if name is not None else settings.demo_profile
    path = (root or _profiles_root()) / profile_name / "profile.yaml"
    if not path.is_file():
        logger.info("No profile.yaml for '%s' (%s); using generic rules only", profile_name, path)
        return DomainProfile(name=profile_name)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Could not read profile %s: %s", path, exc)
        return DomainProfile(name=profile_name)

    patterns: list[UnitPattern] = []
    for item in data.get("unit_patterns", []) or []:
        if not (isinstance(item, (list, tuple)) and len(item) == 3):
            logger.warning("Profile %s: ignoring malformed unit pattern %r", path, item)
            continue
        regex, unit, conversion = (str(x) for x in item)
        try:
            re.compile(regex)
        except re.error as exc:
            logger.warning("Profile %s: invalid regex %r (%s)", path, regex, exc)
            continue
        patterns.append((regex, unit, conversion))
    return DomainProfile(name=profile_name, unit_patterns=tuple(patterns))


__all__ = ["DomainProfile", "load_profile"]
