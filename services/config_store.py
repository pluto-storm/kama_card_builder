"""Small YAML persistence helpers shared by the UI."""

import re

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode


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


def _yaml_sort_key(key):
    return key != "_defaults", str(key).casefold(), str(key)


def _node_line_start(text, index):
    return text.rfind("\n", 0, index) + 1


def _node_line_end(text, index):
    newline = text.find("\n", index)
    return len(text) if newline == -1 else newline + 1


def _dump_yaml_value(value, node=None):
    style = (
        node.style
        if isinstance(value, str)
        and isinstance(node, ScalarNode)
        and node.style in {"'", '"'}
        else None
    )
    if isinstance(value, str) and style is None:
        style = '"'
    flow_style = (
        node.flow_style if isinstance(node, (MappingNode, SequenceNode)) else None
    )
    rendered = yaml.safe_dump(
        value,
        default_style=style,
        default_flow_style=flow_style,
        allow_unicode=True,
        sort_keys=False,
        width=100000,
    ).rstrip("\n")
    if node is None or "\n" not in rendered:
        return rendered
    indent = " " * node.start_mark.column
    if isinstance(value, (dict, list)) and not isinstance(
        node, (MappingNode, SequenceNode)
    ):
        return "\n" + "".join(
            indent + line for line in rendered.splitlines(keepends=True)
        ).rstrip("\n")
    return rendered.replace("\n", "\n" + indent)


def _patch_yaml_text(text, data):
    """Patch changed YAML values in place while retaining surrounding formatting."""
    document = yaml.compose(text)
    if document is None:
        if not data:
            return text
        newline = "\r\n" if "\r\n" in text else "\n"
        addition = yaml.safe_dump(
            _sorted_yaml_data(data),
            sort_keys=False,
            allow_unicode=True,
        ).replace("\n", newline)
        separator = "" if not text or text.endswith(("\n", "\r")) else newline
        return text + separator + addition
    if not isinstance(document, MappingNode) or not isinstance(data, dict):
        raise yaml.YAMLError("YAML document must contain a mapping at the top level.")

    edits = []
    newline = "\r\n" if "\r\n" in text else "\n"

    def patch_mapping(node, old_value, new_value):
        if node.flow_style:
            if old_value != new_value:
                edits.append(
                    (
                        node.start_mark.index,
                        node.end_mark.index,
                        _dump_yaml_value(new_value, node),
                    )
                )
            return

        existing = {}
        for key_node, value_node in node.value:
            if (
                isinstance(key_node, ScalarNode)
                and key_node.tag == "tag:yaml.org,2002:str"
            ):
                existing[key_node.value] = (key_node, value_node)

        for key, (key_node, value_node) in existing.items():
            if key not in new_value:
                start = _node_line_start(text, key_node.start_mark.index)
                end = _node_line_end(text, value_node.end_mark.index)
                edits.append((start, end, ""))
                continue
            old_child = old_value.get(key) if isinstance(old_value, dict) else None
            new_child = new_value[key]
            if old_child == new_child:
                continue
            if (
                isinstance(value_node, MappingNode)
                and isinstance(old_child, dict)
                and isinstance(new_child, dict)
            ):
                patch_mapping(value_node, old_child, new_child)
            elif (
                isinstance(value_node, SequenceNode)
                and isinstance(old_child, list)
                and isinstance(new_child, list)
            ):
                if old_child != new_child:
                    edits.append(
                        (
                            value_node.start_mark.index,
                            value_node.end_mark.index,
                            _dump_yaml_value(new_child, value_node),
                        )
                    )
            else:
                edits.append(
                    (
                        value_node.start_mark.index,
                        value_node.end_mark.index,
                        _dump_yaml_value(new_child, value_node),
                    )
                )

        added = [(key, value) for key, value in new_value.items() if key not in existing]
        if not added:
            return
        added.sort(key=lambda item: _yaml_sort_key(item[0]))
        indent = (
            key_node.start_mark.column
            for key_node, _value_node in node.value
            if isinstance(key_node, ScalarNode)
        )
        indent = next(indent, node.start_mark.column)

        rendered = "".join(
            yaml.safe_dump(
                {key: _sorted_yaml_data(value)},
                sort_keys=False,
                allow_unicode=True,
                width=100000,
            )
            for key, value in added
        )
        prefix = " " * indent
        rendered = "".join(
            prefix + line if line.strip() else line
            for line in rendered.splitlines(keepends=True)
        )
        # Keep existing entries in their original order; insert new keys before
        # the first greater key, otherwise append after the final entry.
        next_node = None
        largest_added_key = max(_yaml_sort_key(key) for key, _ in added)
        for key, (key_node, _value_node) in existing.items():
            if _yaml_sort_key(key) > largest_added_key:
                next_node = key_node
                break

        if next_node is not None:
            position = _node_line_start(text, next_node.start_mark.index)
            while position > 0:
                previous_end = position - 1
                previous_start = _node_line_start(text, previous_end)
                previous_line = text[previous_start:previous_end].strip()
                if previous_line and not previous_line.startswith("#"):
                    break
                position = previous_start
        else:
            last_value = node.value[-1][1]
            position = _node_line_end(text, last_value.end_mark.index)
            if position == len(text) and text and not text.endswith(("\n", "\r")):
                rendered = newline + rendered
        edits.append((position, position, rendered))

    root_value = yaml.safe_load(text)
    patch_mapping(document, root_value, data)
    for start, end, replacement in sorted(edits, reverse=True):
        replacement = replacement.replace("\n", newline)
        text = text[:start] + replacement + text[end:]
    return text


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
