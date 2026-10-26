"""
Module  : framework.core.yaml_loader
Author  : Anil Kalisetti
Purpose : YAML loading that does not turn ``ON`` / ``NO`` / ``yes`` into booleans.

Plain ``yaml.safe_load`` follows YAML 1.1, where these are all booleans. For a QA team that
means the Canadian province code ``ON`` (Ontario) or the country code ``NO`` (Norway) silently
becomes ``True`` / ``False`` in test data. This loader follows the YAML 1.2 rule instead:
only ``true`` and ``false`` (any common capitalisation) are booleans.
"""

from __future__ import annotations

import re
from typing import IO, Any

import yaml

_BOOL_TAG = "tag:yaml.org,2002:bool"


class _StrictBoolLoader(yaml.SafeLoader):
    """SafeLoader with the YAML 1.1 yes/no/on/off boolean spellings removed."""


# Copy the resolver table so the shared yaml.SafeLoader class is never modified.
_StrictBoolLoader.yaml_implicit_resolvers = {
    first_char: [(tag, regex) for tag, regex in resolvers if tag != _BOOL_TAG]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_StrictBoolLoader.add_implicit_resolver(
    _BOOL_TAG, re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")
)


def load_yaml(stream: str | IO[str]) -> Any:
    """Parse YAML text or an open file using the strict boolean rules."""
    return yaml.load(stream, Loader=_StrictBoolLoader)  # noqa: S506 - SafeLoader subclass
