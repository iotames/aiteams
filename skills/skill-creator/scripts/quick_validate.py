#!/usr/bin/env python3
"""
Quick validation script for skills - minimal version
"""

import sys
import os
import re
import json
import yaml
from pathlib import Path

EVALS_SCHEMA_FIELDS = ('id', 'prompt', 'expected_output', 'files', 'expectations')


def validate_evals_json(skill_path: Path, skill_name: str):
    """Validate evals/evals.json against references/schemas.md.

    Returns (ok, message); message is non-empty on warnings.
    """
    evals_file = skill_path / 'evals' / 'evals.json'
    if not evals_file.exists():
        return True, ""
    try:
        data = json.loads(evals_file.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return False, f"evals/evals.json is not valid JSON: {e}"

    if not isinstance(data, dict) or 'skill_name' not in data:
        return False, "evals/evals.json must be an object with a 'skill_name' field"
    if data['skill_name'] != skill_name:
        return False, (
            f"evals/evals.json 'skill_name' ({data['skill_name']!r}) does not "
            f"match frontmatter 'name' ({skill_name!r})"
        )

    evals = data.get('evals')
    if not isinstance(evals, list) or not evals:
        return False, "evals/evals.json 'evals' must be a non-empty list"

    for i, item in enumerate(evals):
        if not isinstance(item, dict):
            return False, f"evals[{i}] must be an object"
        for field in ('id', 'prompt', 'expected_output'):
            if field not in item:
                return False, f"evals[{i}] missing required field '{field}'"
        if not isinstance(item['id'], int):
            return False, f"evals[{i}].id must be an integer"
        for field in ('prompt', 'expected_output'):
            if not isinstance(item[field], str) or not item[field].strip():
                return False, f"evals[{i}].{field} must be a non-empty string"
        for field in ('files', 'expectations'):
            if field in item:
                if not isinstance(item[field], list) or not all(isinstance(x, str) for x in item[field]):
                    return False, f"evals[{i}].{field} must be a list of strings"
        unknown = set(item) - set(EVALS_SCHEMA_FIELDS)
        if unknown:
            return True, (
                f"evals[{i}] has fields outside the schema {sorted(unknown)}; "
                f"allowed: {sorted(EVALS_SCHEMA_FIELDS)} (see references/schemas.md)"
            )
    return True, ""


def validate_skill(skill_path):
    """Basic validation of a skill"""
    skill_path = Path(skill_path).resolve()

    # Check SKILL.md exists
    skill_md = skill_path / 'SKILL.md'
    if not skill_md.exists():
        return False, "SKILL.md not found"

    # Read and validate frontmatter
    try:
        content = skill_md.read_text(encoding="utf-8-sig")  # utf-8-sig strips a leading BOM
    except UnicodeDecodeError:
        return False, "SKILL.md is not valid UTF-8 text"
    if not content.startswith('---'):
        return False, "No YAML frontmatter found"

    # Extract frontmatter (tolerate CRLF line endings)
    match = re.match(r'^---[\r\n]+(.*?)[\r\n]+---', content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    warnings: list[str] = []

    frontmatter_text = match.group(1)

    # Parse YAML frontmatter
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        if not isinstance(frontmatter, dict):
            return False, "Frontmatter must be a YAML dictionary"
    except yaml.YAMLError as e:
        return False, f"Invalid YAML in frontmatter: {e}"

    # Define allowed properties
    ALLOWED_PROPERTIES = {'name', 'description', 'license', 'allowed-tools', 'metadata', 'compatibility'}

    # Check for unexpected properties (excluding nested keys under metadata)
    unexpected_keys = set(frontmatter.keys()) - ALLOWED_PROPERTIES
    if unexpected_keys:
        return False, (
            f"Unexpected key(s) in SKILL.md frontmatter: {', '.join(sorted(unexpected_keys))}. "
            f"Allowed properties are: {', '.join(sorted(ALLOWED_PROPERTIES))}"
        )

    # Check required fields
    if 'name' not in frontmatter:
        return False, "Missing 'name' in frontmatter"
    if 'description' not in frontmatter:
        return False, "Missing 'description' in frontmatter"

    # Extract name for validation
    name = frontmatter.get('name', '')
    if not isinstance(name, str):
        return False, f"Name must be a string, got {type(name).__name__}"
    name = name.strip()
    if not name:
        return False, "Name must not be empty"

    # Check naming convention (kebab-case: lowercase with hyphens)
    if not re.match(r'^[a-z0-9-]+$', name):
        return False, f"Name '{name}' should be kebab-case (lowercase letters, digits, and hyphens only)"
    if name.startswith('-') or name.endswith('-') or '--' in name:
        return False, f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens"
    # Check name length (max 64 characters per spec)
    if len(name) > 64:
        return False, f"Name is too long ({len(name)} characters). Maximum is 64 characters."
    # Check name matches parent directory name (spec requirement)
    if skill_path.name != name:
        return False, (
            f"Name '{name}' does not match the parent directory name "
            f"'{skill_path.name}'. The spec requires the name field to match "
            "the skill's directory name."
        )

    # Extract and validate description
    description = frontmatter.get('description', '')
    if not isinstance(description, str):
        return False, f"Description must be a string, got {type(description).__name__}"
    description = description.strip()
    if not description:
        return False, "Description must not be empty"
    # Check for angle brackets
    if '<' in description or '>' in description:
        return False, "Description cannot contain angle brackets (< or >)"
    # Check description length (max 1024 characters per spec)
    if len(description) > 1024:
        return False, f"Description is too long ({len(description)} characters). Maximum is 1024 characters."

    # Validate compatibility field if present (optional)
    compatibility = frontmatter.get('compatibility', '')
    if compatibility:
        if not isinstance(compatibility, str):
            return False, f"Compatibility must be a string, got {type(compatibility).__name__}"
        if len(compatibility) > 500:
            return False, f"Compatibility is too long ({len(compatibility)} characters). Maximum is 500 characters."

    # Validate allowed-tools format if present (spec: space-separated string)
    allowed_tools = frontmatter.get('allowed-tools')
    if allowed_tools is not None:
        if isinstance(allowed_tools, list):
            return False, (
                "'allowed-tools' must be a space-separated string, not a YAML list. "
                f"Example: allowed-tools: Read Write Bash(git:*)"
            )
        if not isinstance(allowed_tools, str) or not allowed_tools.strip():
            return False, "'allowed-tools' must be a non-empty space-separated string"
        if ',' in allowed_tools:
            return False, (
                "'allowed-tools' must be space-separated, not comma-separated: "
                f"{allowed_tools!r}"
            )

    # Validate metadata field if present (spec: map of string -> string)
    metadata = frontmatter.get('metadata')
    if metadata is not None:
        if not isinstance(metadata, dict):
            return False, "'metadata' must be a YAML mapping (map of string to string)"
        for k, v in metadata.items():
            if not isinstance(k, str) or not isinstance(v, str):
                return False, (
                    "'metadata' keys and values must all be strings; "
                    f"got key={k!r} type={type(v).__name__}"
                )

    # Validate evals.json against the schema in references/schemas.md (if present)
    eval_ok, eval_msg = validate_evals_json(skill_path, name)
    if not eval_ok:
        return False, eval_msg
    if eval_msg:
        warnings.append(eval_msg)

    # Warn (not fail) when a LICENSE file exists but no license field is declared
    license_field = frontmatter.get('license')
    has_license_file = (skill_path / 'LICENSE.txt').exists() or (skill_path / 'LICENSE').exists()
    if has_license_file and not license_field:
        warnings.append(
            "Bundled license file found but 'license' field is missing in frontmatter. "
            "Consider adding e.g. 'license: Apache-2.0'."
        )

    message = "Skill is valid!"
    if warnings:
        message += "\n" + "\n".join(f"Warning: {w}" for w in warnings)
    return True, message

if __name__ == "__main__":
    # Inline copy so the script also works when run directly as
    # `python scripts/quick_validate.py <skill_directory>` (no package context).
    import sys as _sys
    for _stream in (_sys.stdout, _sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.quick_validate <skill_directory>")
        sys.exit(1)
    
    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)