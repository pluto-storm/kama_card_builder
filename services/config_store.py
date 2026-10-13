"""Small YAML persistence helpers shared by the UI."""

import re

import yaml
from yaml.nodes import MappingNode, ScalarNode


def _sorted_yaml_data(value):
    if isinstance(value, dict):
        keys = sorted(
            value,
            key=lambda key: (
                key != "_defaults",
                str(key).casefold(),
                str(key),
            ),
        )
        return {key: _sorted_yaml_data(value[key]) for key in keys}
    if isinstance(value, list):
        return [_sorted_yaml_data(item) for item in value]
    return value


def _top_level_inline_comments(text):
    document = yaml.compose(text)
    if not isinstance(document, MappingNode):
        return {}
    lines = text.splitlines()
    comments = {}
    for key_node, _value_node in document.value:
        if not isinstance(key_node, ScalarNode) or key_node.tag != "tag:yaml.org,2002:str":
            continue
        line = lines[key_node.start_mark.line]
        suffix = line[key_node.end_mark.column :]
        match = re.match(r"^\s*:\s*#(.*)$", suffix)
        if match:
            comments[key_node.value] = match.group(1).strip()
    return comments


def _restore_top_level_inline_comments(text, comments):
    if not comments:
        return text
    document = yaml.compose(text)
    if not isinstance(document, MappingNode):
        return text
    lines = text.splitlines()
    for key_node, _value_node in document.value:
        if not isinstance(key_node, ScalarNode) or key_node.value not in comments:
            continue
        line_index = key_node.start_mark.line
        lines[line_index] = f"{lines[line_index].rstrip()}  #{comments[key_node.value]}"
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _write_sorted_yaml(path, data):
    path.write_text(
        yaml.safe_dump(
            _sorted_yaml_data(data),
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def _update_yaml_scalars(path, updates):
    text = path.read_text(encoding="utf-8")
    document = yaml.compose(text)
    if document is not None and not isinstance(document, MappingNode):
        raise yaml.YAMLError(f"{path} must contain a YAML mapping at the top level.")

    replacements = []
    found = set()
    if isinstance(document, MappingNode):
        for key_node, value_node in document.value:
            if not isinstance(key_node, ScalarNode):
                continue
            key = key_node.value
            if key not in updates:
                continue
            scalar_text = yaml.safe_dump(
                updates[key],
                default_style='"',
                allow_unicode=True,
                width=100000,
            ).rstrip("\n")
            replacements.append(
                (value_node.start_mark.index, value_node.end_mark.index, scalar_text)
            )
            found.add(key)

    for start, end, scalar_text in reversed(replacements):
        text = text[:start] + scalar_text + text[end:]

    missing = [key for key in updates if key not in found]
    if missing:
        if text and not text.endswith(("\n", "\r")):
            text += "\n"
        for key in missing:
            scalar_text = yaml.safe_dump(
                updates[key],
                default_style='"',
                allow_unicode=True,
                width=100000,
            ).rstrip("\n")
            text += f"{key}: {scalar_text}\n"

    path.write_text(text, encoding="utf-8")


def _ensure_local_config(local_path, example_path):
    if local_path.exists():
        return
    example_text = example_path.read_text(encoding="utf-8")
    try:
        with local_path.open("x", encoding="utf-8", newline="") as local_file:
            local_file.write(example_text)
    except FileExistsError:
        pass


def _model_metadata_template(kind):
    if kind == "lora":
        return (
            "# Optional LoRA metadata. Uncomment and fill in the fields you need.\n"
            "# base_model: pony\n"
            "# source: https://example.com/model\n"
            "# prompt: trigger words or style description\n"
            "# trigger_words:\n"
            "#   - example_trigger\n"
            "# default_weight: 0.7\n"
        )
    return (
        "# Optional checkpoint metadata. Uncomment and fill in the fields you need.\n"
        "# name: Display Name\n"
        "# base_model: pony\n"
        "# source: https://example.com/model\n"
        "# sampler_defaults:\n"
        "#   steps: 30\n"
        "#   cfg: 7\n"
        "#   sampler: dpmpp_2m\n"
        "#   scheduler: karras\n"
    )
