"""Small YAML persistence helpers shared by the UI."""

import yaml


def _sorted_yaml_data(value):
    if isinstance(value, dict):
        keys = sorted(value, key=lambda key: (str(key).casefold(), str(key)))
        return {key: _sorted_yaml_data(value[key]) for key in keys}
    if isinstance(value, list):
        return [_sorted_yaml_data(item) for item in value]
    return value


def _write_sorted_yaml(path, data):
    path.write_text(
        yaml.safe_dump(
            _sorted_yaml_data(data),
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


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
