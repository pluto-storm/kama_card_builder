#!/usr/bin/env python3
"""
Collects everything needed to run a batch of ComfyUI generations.

Stage 1 (this file): read yamls -> validate -> build a list of fully resolved jobs.
Stage 2 (later):     feed each job into the ComfyUI workflow.

Usage:
    python run.py                  # build jobs, print a summary
    python run.py --verbose        # print every job
    python run.py --json jobs.json # also dump jobs to a json file
    python run.py --skip-file-check  # don't require model files to exist on disk

------------------------------------------------------------------------------
EXPECTED YAML SCHEMAS
------------------------------------------------------------------------------

paths.local.yaml  (${var} references to other keys are expanded)
    comfyui_root: /home/me/ComfyUI
    checkpoints_dir: ${comfyui_root}/models/checkpoints
    loras_dir: ${comfyui_root}/models/loras
    output_dir: ./output

generate.local.yaml
    mode: generate_images                 # generate images+depth, or depth_maps
    checkpoint_to_use: sdxl_base          # key in workflow/checkpoints.yaml
    sets_to_generate: [set_0, set_1]      # keys in card_prompts/cards.yaml
    seeds: [1, 2, 3]                      # optional; explicit seeds, OR
    images_per_card: 1                    # optional; random seeds if neither seed option is set
    seed_start: 0                         # optional; deterministic first seed for images_per_card
    prompt_pos_prefix: "masterpiece"      # optional; put before everything
    prompt_pos_suffix: ""                 # optional; put after everything
    prompt_neg: "blurry, watermark"       # optional; global negative
    settings: {steps: 30, cfg: 6.5}       # optional; overrides checkpoint settings

workflow/checkpoints.yaml
    sdxl_base:
      file: sd_xl_base_1.0.safetensors    # relative to checkpoints_dir
      base_model: sdxl                    # optional, used for LoRA compatibility check
      settings: {steps: 30, cfg: 6.5, sampler: dpmpp_2m, scheduler: karras}

workflow/loras.yaml
    lora_presets:
      preset_1:
        - {name: kim_lora, weight: 0.8}
        - {name: other_lora, weight: 0.5}
    kim_lora:
      file: characters/kim_v2.safetensors # relative to loras_dir
      base_model: sdxl                    # optional
      prompt: kim style                   # optional positive-prompt text
      trigger_words: [kim_possible]       # optional (list or string)
    default_weight: 0.85                # optional (falls back to 0.7)

card_prompts/characters|outfits|poses|places.yaml
    some_entry:
      prompt: "positive prompt text"
      prompt_neg: "optional negative text"
      default_display: "NAME"             # optional, passed through for card text
            lora:                               # optional list of names or {name, weight}
                - kim_lora
        - {name: other_lora, weight: 0.5}

card_prompts/cards.yaml
    set_0:
      set_defaults:
        character: kim_possible
        prompt_pos: "school uniform"
      card_1:
        outfit: kim_possible_student
        pose: thinking
        place: school
      card_2:
        outfit: kim_possible_spy
        pose: proud
        place: blank

    # card entries inherit set_defaults unless they override them; individual
    # card fields still win over the shared defaults.
------------------------------------------------------------------------------
"""

import argparse
import json
import re
import secrets
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
CARD_DIR = ROOT / "card_prompts"
WORKFLOW_DIR = ROOT / "workflow"
DEPTH_INPUT_DIR = ROOT / "depths" / "inputs"
DEPTH_OUTPUT_DIR = ROOT / "depths" / "outputs"

# Order matters: prompts are assembled in this order, and later LoRA
# references override model and CLIP strengths from earlier ones.
LIBRARY_KINDS = ["character", "outfit", "pose", "place"]
LIBRARY_FILES = {
    "character": "characters.yaml",
    "outfit": "outfits.yaml",
    "pose": "poses.yaml",
    "place": "places.yaml",
}


class ConfigError(Exception):
    pass


class DuplicateKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConfigError(f"Duplicate YAML key '{key}'")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


DuplicateKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


# ----------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------

def load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"Missing file: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.load(f, Loader=DuplicateKeyLoader)
    except yaml.YAMLError as e:
        raise ConfigError(f"Could not parse {path}:\n{e}")
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return data


def expand_vars(value, variables: dict, *, label: str = "config", depth: int = 0):
    """Expand ${var} references recursively using a provided variable map."""
    if depth > 10:
        raise ConfigError(f"{label}: circular ${var} reference")

    pattern = re.compile(r"\$\{(\w+)\}")

    def sub(match):
        key = match.group(1)
        if key not in variables:
            raise ConfigError(f"{label}: unknown variable ${{{key}}}")
        return str(expand_vars(variables[key], variables, label=label, depth=depth + 1))

    return pattern.sub(sub, str(value)).replace("\\", "/") if isinstance(value, str) else value


def load_paths() -> dict:
    """Load paths.local.yaml and expand ${var} references and ~."""
    raw = load_yaml(ROOT / "paths.local.yaml")
    resolved = {}
    for key, value in raw.items():
        text = expand_vars(value, raw, label="paths.local.yaml")
        if key.endswith(("_dir", "_root")):
            resolved[key] = Path(text).expanduser()
        else:
            resolved[key] = text
    return resolved


def require_path(paths: dict, key: str) -> Path:
    if key not in paths:
        raise ConfigError(f"paths.local.yaml is missing required key '{key}'")
    return paths[key]


def load_library() -> dict:
    lib = {kind: load_yaml(CARD_DIR / fname) for kind, fname in LIBRARY_FILES.items()}
    lib["cards"] = load_yaml(CARD_DIR / "cards.yaml")
    lib["checkpoints"] = load_yaml(WORKFLOW_DIR / "checkpoints.yaml")
    lib["loras"] = load_yaml(WORKFLOW_DIR / "loras.yaml")
    return lib


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def join_prompt(parts) -> str:
    """Join non-empty prompt fragments with ', ', cleaning stray commas/spaces."""
    cleaned = []
    for p in parts:
        if not p:
            continue
        p = str(p).strip().strip(",").strip()
        if p:
            cleaned.append(p)
    return ", ".join(cleaned)


def as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def normalize_lora_refs(refs, where: str) -> list:
    """Normalize LoRA references into (name, weight, clip) tuples."""
    out = []
    if isinstance(refs, (str, dict)):
        refs = [refs]
    for ref in refs or []:
        if isinstance(ref, str):
            out.append((ref, None, None))
        elif isinstance(ref, dict) and "name" in ref:
            out.append((ref["name"], ref.get("weight"), ref.get("clip")))
        else:
            raise ConfigError(
                f"{where}: lora entries must be a name or {{name:, weight:, clip:}}, got {ref!r}"
            )
    return out


def resolve_lora_preset(preset_name: str, lib: dict, where: str) -> list:
    """Resolve a named preset in workflow/loras.yaml['lora_presets']."""
    presets = (lib.get("loras") or {}).get("lora_presets") or {}
    if preset_name not in presets:
        raise ConfigError(f"{where}: lora_preset '{preset_name}' not found in workflow/loras.yaml")
    return normalize_lora_refs(presets[preset_name], f"{where} (preset '{preset_name}')")


VALID_CARD_FIELDS = {
    "character",
    "outfit",
    "pose",
    "place",
    "prompt_pos",
    "prompt_neg",
    "loras",
    "lora_preset",
}


def validate_library(lib: dict) -> None:
    """Validate the shared prompt and workflow libraries used by contributors."""
    cards = lib.get("cards") or {}
    for set_name, set_data in cards.items():
        if not isinstance(set_data, dict):
            raise ConfigError(f"cards.yaml set '{set_name}' must be a mapping")

        defaults = set_data.get("set_defaults") or {}
        if defaults and not isinstance(defaults, dict):
            raise ConfigError(f"cards.yaml set '{set_name}': set_defaults must be a mapping")

        unknown = sorted(set(defaults) - VALID_CARD_FIELDS)
        if unknown:
            raise ConfigError(
                f"cards.yaml set '{set_name}': unsupported set_defaults field(s): {', '.join(unknown)}"
            )

        for card_name, card in set_data.items():
            if card_name == "set_defaults":
                continue
            if not isinstance(card, dict):
                raise ConfigError(f"cards.yaml set '{set_name}' card '{card_name}' must be a mapping")
            unknown = sorted(set(card) - VALID_CARD_FIELDS)
            if unknown:
                raise ConfigError(
                    f"cards.yaml set '{set_name}' card '{card_name}': unsupported field(s): {', '.join(unknown)}"
                )

            if "lora_preset" in card:
                preset = card["lora_preset"]
                if not isinstance(preset, str):
                    raise ConfigError(
                        f"cards.yaml set '{set_name}' card '{card_name}': lora_preset must be a string"
                    )
                if preset not in (lib.get("loras") or {}).get("lora_presets", {}):
                    raise ConfigError(
                        f"cards.yaml set '{set_name}' card '{card_name}': unknown lora_preset '{preset}'"
                    )

    for kind in LIBRARY_KINDS:
        table = lib.get(kind) or {}
        for key, value in table.items():
            if not isinstance(value, dict):
                raise ConfigError(f"{LIBRARY_FILES[kind]} entry '{key}' must be a mapping")

    loras = lib.get("loras") or {}
    presets = loras.get("lora_presets") or {}
    if not isinstance(presets, dict):
        raise ConfigError("workflow/loras.yaml: lora_presets must be a mapping")
    for preset_name, refs in presets.items():
        if not isinstance(refs, list):
            raise ConfigError(f"workflow/loras.yaml: lora_preset '{preset_name}' must be a list")
        for ref in refs:
            if isinstance(ref, str):
                continue
            if not isinstance(ref, dict) or "name" not in ref:
                raise ConfigError(
                    f"workflow/loras.yaml: preset '{preset_name}' entries must be strings or mappings with a name field"
                )


def resolve_seeds(gen: dict) -> list:
    if "seeds" in gen:
        seeds = gen["seeds"]
        if not isinstance(seeds, list) or not seeds:
            raise ConfigError("generate.local.yaml: 'seeds' must be a non-empty list")
        return seeds
    n = int(gen.get("images_per_card", 1))
    if "seed_start" in gen:
        start = int(gen["seed_start"])
        return [start + i for i in range(n)]
    return [secrets.randbits(64) for _ in range(n)]


# ----------------------------------------------------------------------------
# Job building
# ----------------------------------------------------------------------------

def build_jobs(gen: dict, paths: dict, lib: dict) -> tuple:
    """Returns (jobs, errors). Errors are collected so you see all problems at once."""
    errors = []

    # --- checkpoint -------------------------------------------------------
    ckpt_name = gen.get("checkpoint_to_use")
    if not ckpt_name:
        raise ConfigError("generate.local.yaml: 'checkpoint_to_use' is required")
    if ckpt_name not in lib["checkpoints"]:
        raise ConfigError(
            f"checkpoint '{ckpt_name}' not found in workflow/checkpoints.yaml. "
            f"Available: {', '.join(lib['checkpoints']) or '(none)'}"
        )
    ckpt = lib["checkpoints"][ckpt_name]
    if "file" not in ckpt:
        raise ConfigError(f"checkpoint '{ckpt_name}' has no 'file' field")
    ckpt_path = Path(require_path(paths, "checkpoints_dir")) / expand_vars(ckpt["file"], paths, label=f"checkpoint '{ckpt_name}'")
    loras_dir = require_path(paths, "loras_dir")

    # settings: checkpoint defaults overridden by generate.local.yaml
    settings = {
        **(ckpt.get("sampler_defaults") or {}),
        **(ckpt.get("settings") or {}),
        **(gen.get("settings") or {}),
    }
    image_size = gen.get("image_size")
    if image_size is not None:
        if not isinstance(image_size, dict) or set(image_size) != {"width", "height"}:
            raise ConfigError(
                "generate.local.yaml: 'image_size' must contain exactly 'width' and 'height'"
            )
        for dimension, value in image_size.items():
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ConfigError(
                    f"generate.local.yaml: image_size.{dimension} must be a positive integer"
                )

    # --- sets -------------------------------------------------------------
    sets = gen.get("sets_to_generate")
    if not sets:
        raise ConfigError("generate.local.yaml: 'sets_to_generate' is required")
    sets = as_list(sets)

    seeds = resolve_seeds(gen)
    jobs = []

    for set_name in sets:
        if set_name not in lib["cards"]:
            errors.append(
                f"set '{set_name}' not found in cards.yaml "
                f"(available: {', '.join(lib['cards'])})"
            )
            continue

        set_data = lib["cards"][set_name] or {}
        defaults = set_data.get("set_defaults") or {}
        if defaults and not isinstance(defaults, dict):
            errors.append(f"set '{set_name}': set_defaults must be a mapping")
            continue

        for card_name, card in set_data.items():
            if card_name == "set_defaults":
                continue
            if not isinstance(card, dict):
                errors.append(f"{set_name}/{card_name}: card must be a mapping")
                continue

            merged_card = {**defaults, **card}
            where = f"{set_name}/{card_name}"
            try:
                base = build_card(where, merged_card, gen, lib, loras_dir, ckpt, ckpt_name, paths)
            except ConfigError as e:
                errors.append(str(e))
                continue

            for seed in seeds:
                jobs.append(
                    {
                        "job_id": f"{set_name}__{card_name}__seed{seed}",
                        "set": set_name,
                        "card": card_name,
                        "seed": seed,
                        "checkpoint": {
                            "name": ckpt_name,
                            "path": str(ckpt_path),
                            "base_model": ckpt.get("base_model"),
                        },
                        "settings": settings,
                        "image_size": image_size,
                        **base,
                    }
                )

    return jobs, errors


def build_card(where, card, gen, lib, loras_dir, ckpt, ckpt_name, paths) -> dict:
    """Resolve one card into prompts, loras, and display text (seed-independent)."""
    if not isinstance(card, dict):
        raise ConfigError(f"{where}: card must be a mapping")

    # Support both the older script-specific names and the repo's actual config names.
    pos_parts = [gen.get("global_positive"), gen.get("prompt_pos_prefix")]
    neg_parts = [gen.get("global_negative"), gen.get("prompt_neg")]
    lora_refs = []  # ordered; later entries override earlier ones
    display = {}

    # library entries: character -> outfit -> pose -> place
    entries = []
    for kind in LIBRARY_KINDS:
        key = card.get(kind)
        if key is None:
            continue
        table = lib[kind]
        if key not in table:
            raise ConfigError(
                f"{where}: {kind} '{key}' not found in {LIBRARY_FILES[kind]}"
            )
        entry = table[key] or {}
        entries.append((kind, key, entry))

    for kind, key, entry in entries:
        pos_parts.append(entry.get("prompt"))
        neg_parts.append(entry.get("prompt_neg"))
        lora_refs += normalize_lora_refs(entry.get("lora"), f"{where} ({kind} '{key}')")
        lora_refs += normalize_lora_refs(entry.get("loras"), f"{where} ({kind} '{key}')")
        display[kind] = {"key": key, "text": entry.get("default_display")}

    # preset-based groupings and card-level extras (most specific)
    for preset_name in as_list(card.get("lora_preset")):
        lora_refs += resolve_lora_preset(preset_name, lib, where)

    pos_parts.append(card.get("prompt_pos"))
    neg_parts.append(card.get("prompt_neg"))
    lora_refs += normalize_lora_refs(card.get("loras"), where)
    pos_parts.append(gen.get("prompt_pos_suffix"))

    # --- merge loras ------------------------------------------------------
    merged = {}  # name -> (weight, clip); dict preserves first-seen order
    for name, weight, clip in lora_refs:
        if name not in lib["loras"]:
            raise ConfigError(f"{where}: lora '{name}' not found in workflow/loras.yaml")
        entry = lib["loras"][name] or {}
        if weight is None:
            weight = entry.get("default_weight", 0.7)
        weight = float(weight)
        merged[name] = (weight, weight if clip is None else float(clip))

    lora_list = []
    trigger_words = []
    lora_prompts = []
    for name, (weight, clip) in merged.items():
        entry = lib["loras"][name] or {}
        if "file" not in entry:
            raise ConfigError(f"{where}: lora '{name}' has no 'file' field")

        lora_base, ckpt_base = entry.get("base_model"), ckpt.get("base_model")
        if lora_base and ckpt_base and lora_base != ckpt_base:
            raise ConfigError(
                f"{where}: lora '{name}' is for '{lora_base}' but checkpoint "
                f"'{ckpt_name}' is '{ckpt_base}'"
            )

        for word in as_list(entry.get("trigger_words")):
            if word not in trigger_words:
                trigger_words.append(word)
        for prompt in as_list(entry.get("prompt")):
            if prompt not in lora_prompts:
                lora_prompts.append(prompt)

        lora_path = expand_vars(entry["file"], paths, label=f"lora '{name}'")
        lora_list.append(
            {
                "name": name,
                "path": str(Path(loras_dir) / lora_path),
                "weight": weight,
                "clip": clip,
            }
        )

    # Trigger words and LoRA prompts go first so they are not lost behind a long prompt.
    positive = join_prompt(
        [join_prompt(trigger_words), join_prompt(lora_prompts)] + pos_parts
    )
    negative = join_prompt(neg_parts)

    return {
        "positive": positive,
        "negative": negative,
        "loras": lora_list,
        "display": display,
    }


def check_files(jobs) -> list:
    """Verify every checkpoint/lora file referenced actually exists on disk."""
    problems = []
    seen = set()
    for job in jobs:
        files = [("checkpoint", job["checkpoint"]["name"], job["checkpoint"]["path"])]
        files += [("lora", l["name"], l["path"]) for l in job["loras"]]
        for kind, name, path in files:
            if path in seen:
                continue
            seen.add(path)
            if not Path(path).exists():
                problems.append(f"{kind} '{name}': file not found at {path}")
    return problems


def build_depth_jobs() -> list:
    """Recursively resolve images under depths/inputs into depth-only jobs."""
    if not DEPTH_INPUT_DIR.is_dir():
        raise ConfigError(f"Depth input directory does not exist: {DEPTH_INPUT_DIR}")
    supported_extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    jobs = []
    output_paths = set()
    images = sorted(
        (
            path
            for path in DEPTH_INPUT_DIR.rglob("*")
            if path.is_file()
            and path.suffix.lower() in supported_extensions
        ),
        key=lambda path: path.relative_to(DEPTH_INPUT_DIR).as_posix().lower(),
    )
    output_name_counts = {}
    for image in images:
        relative_path = image.relative_to(DEPTH_INPUT_DIR)
        output_key = (
            DEPTH_OUTPUT_DIR / relative_path.parent / f"{image.stem}.png"
        ).as_posix().casefold()
        output_name_counts[output_key] = output_name_counts.get(output_key, 0) + 1

    for image in images:
        relative_path = image.relative_to(DEPTH_INPUT_DIR)
        output_stem = image.stem
        output_path = (
            DEPTH_OUTPUT_DIR
            / relative_path.parent
            / f"{output_stem}.png"
        )
        output_key = output_path.as_posix().casefold()
        if output_name_counts[output_key] > 1:
            output_stem += f"_{image.suffix.lstrip('.').lower()}"
            output_path = output_path.with_name(f"{output_stem}.png")
            output_key = output_path.as_posix().casefold()
        collision_suffix = 2
        while output_key in output_paths:
            output_path = output_path.with_name(
                f"{output_stem}_{collision_suffix}.png"
            )
            output_key = output_path.as_posix().casefold()
            collision_suffix += 1
        output_paths.add(output_key)
        jobs.append(
            {
                "job_id": f"depth__{relative_path.as_posix()}",
                "set": relative_path.parent.as_posix(),
                "card": image.stem,
                "input_path": str(image.resolve()),
                "output_path": str(output_path),
            }
        )

    if not jobs:
        raise ConfigError(f"No supported images found under {DEPTH_INPUT_DIR}")
    return jobs


# ----------------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------------

def print_job(job, indent="  "):
    print(f"{indent}{job['job_id']}")
    print(f"{indent}  positive: {job['positive']}")
    print(f"{indent}  negative: {job['negative']}")
    loras = ", ".join(f"{l['name']}@{l['weight']}" for l in job["loras"]) or "(none)"
    print(f"{indent}  loras:    {loras}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--verbose", "-v", action="store_true", help="print every job")
    ap.add_argument("--json", metavar="FILE", help="write resolved jobs to a json file")
    ap.add_argument(
        "--skip-file-check",
        action="store_true",
        help="don't require checkpoint/lora files to exist locally",
    )
    ap.add_argument(
        "--generate",
        default="generate.local.yaml",
        help="generate config to use (default: generate.local.yaml)",
    )
    ap.add_argument(
        "--no-submit",
        action="store_true",
        help="build the run without submitting jobs to ComfyUI",
    )
    args = ap.parse_args()

    try:
        paths = load_paths()
        gen = load_yaml(ROOT / args.generate)
        mode = gen.get("mode", "generate_images")
        if mode == "generate_images":
            lib = load_library()
            validate_library(lib)
            jobs, errors = build_jobs(gen, paths, lib)
            template_path = WORKFLOW_DIR / "image_gen_w_depth.json"
        elif mode == "depth_maps":
            jobs = build_depth_jobs()
            errors = []
            template_path = WORKFLOW_DIR / "image_gen_depth.json"
        else:
            raise ConfigError(
                "generate.local.yaml: 'mode' must be 'generate_images' or 'depth_maps'"
            )
    except ConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if mode == "generate_images" and not args.skip_file_check:
        errors += check_files(jobs)

    if errors:
        print(f"Found {len(errors)} problem(s):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    # summary
    mode_label = (
        "Image generation (image + depth output)"
        if mode == "generate_images"
        else "Depth maps from existing images"
    )
    print(f"Mode:       {mode_label}")
    if mode == "generate_images":
        print(f"Checkpoint: {gen['checkpoint_to_use']}")
        print(f"Sets:       {', '.join(as_list(gen['sets_to_generate']))}")
    else:
        print(f"Input images: {len(jobs)}")
        print(f"Depth outputs: {DEPTH_OUTPUT_DIR}")
    print(f"Jobs:       {len(jobs)}")
    print()
    to_show = jobs if args.verbose else jobs[:3]
    for job in to_show:
        if mode == "depth_maps":
            print(f"  {job['job_id']}")
            print(f"    input: {job['input_path']}")
            print(f"    output: {job['output_path']}")
        else:
            print_job(job)
    if not args.verbose and len(jobs) > 3:
        print(f"  ... {len(jobs) - 3} more (use --verbose to see all)")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=2)
        print(f"\nWrote {len(jobs)} jobs to {args.json}")

    workflow_input = {
        "mode": mode,
        "jobs": jobs,
        "paths": {key: str(value) for key, value in paths.items()},
        "template_path": str(template_path),
        "submit": not args.no_submit,
    }
    try:
        subprocess.run(
            [sys.executable, str(ROOT / "comfyui_workflow.py")],
            input=json.dumps(workflow_input),
            text=True,
            check=True,
            cwd=ROOT,
        )
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"ERROR: ComfyUI workflow generation failed: {e}", file=sys.stderr)
        sys.exit(1)

    return jobs


if __name__ == "__main__":
    main()