"""Path and display helpers for local model catalog entries."""

import re
from pathlib import Path

import generation


def asset_file_path(kind, name, entry, raw_paths, root):
    file_value = entry.get("file")
    if not isinstance(file_value, str) or not file_value.strip():
        raise generation.ConfigError(f"{kind} '{name}' has no file path")
    base_key = "loras_dir" if kind == "loras" else "checkpoints_dir"
    if base_key not in raw_paths:
        raise generation.ConfigError(
            f"Setup is missing the image-generation path '{base_key}'"
        )
    expanded = generation.expand_vars(
        file_value, raw_paths, label=f"{kind} '{name}'"
    )
    file_path = Path(expanded).expanduser()
    if not file_path.is_absolute():
        base = Path(
            generation.expand_vars(
                raw_paths[base_key], raw_paths, label=f"paths.local.yaml '{base_key}'"
            )
        ).expanduser()
        if not base.is_absolute():
            base = root / base
        file_path = base / file_path
    return file_path


def asset_display_name(kind, name, entry, raw_paths, file_path, root):
    if kind != "loras":
        return name

    file_value = entry.get("file")
    loras_root_value = raw_paths.get("loras_dir")
    if not isinstance(file_value, str) or not loras_root_value:
        return name

    try:
        loras_root = Path(
            generation.expand_vars(
                loras_root_value,
                raw_paths,
                label="paths.local.yaml 'loras_dir'",
            )
        ).expanduser()
    except generation.ConfigError:
        return name
    if not loras_root.is_absolute():
        loras_root = root / loras_root
    loras_root = loras_root.resolve()

    variable_match = re.match(r"^\$\{(\w+)\}(?:[/\\](.*))?$", file_value)
    relative_path = None
    prefix = ""
    if variable_match:
        variable_name, suffix = variable_match.groups()
        if variable_name == "loras_dir":
            relative_path = suffix or ""
        elif variable_name in raw_paths:
            try:
                variable_path = Path(
                    generation.expand_vars(
                        raw_paths[variable_name],
                        raw_paths,
                        label=f"paths.local.yaml '{variable_name}'",
                    )
                ).expanduser()
            except generation.ConfigError:
                variable_path = None
            if variable_path is not None:
                if not variable_path.is_absolute():
                    variable_path = root / variable_path
                try:
                    variable_path.resolve().relative_to(loras_root)
                except ValueError:
                    pass
                else:
                    relative_path = suffix or ""
                    prefix = f"{{{variable_name}}}/"

    if relative_path is None and file_path is not None:
        try:
            relative_path = str(file_path.resolve().relative_to(loras_root))
        except ValueError:
            return name
    if relative_path is None:
        return name

    relative_path = relative_path.replace("\\", "/").strip("/")
    stem = Path(relative_path).with_suffix("").as_posix()
    return f"{prefix}{stem}" if stem else name


def asset_tag(item):
    if not item or item.get("path") is None:
        return "unconfigured"
    return "installed" if item["path"].is_file() else "missing"
