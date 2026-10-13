# Kama Card Builder

Kama Card Builder is a desktop interface for preparing and running ComfyUI image and depth workflows. Card prompts, reusable prompt entries, checkpoints, and LoRAs are still stored as YAML and can be edited directly.

## Launch

1. Install Python 3.10 or newer.
2. Install the project dependency:

   ```sh
   python -m pip install -r requirements.txt
   ```

3. Start ComfyUI and run:

   ```sh
   python run.py
   ```

   On launch, the UI creates `paths.local.yaml` and `generate.local.yaml` from their example files if they do not already exist. Existing local files are left unchanged. Set your machine-specific paths in the Setup tab and save them before generating.

## Use the UI

- **Setup** edits paths used by both workflows separately from image-only checkpoint, LoRA, and image-output paths. The ComfyUI root, ComfyUI output, server URL, and Geometry Estimation model file are shared settings required for depth and image generation. The model browser starts at `<comfyui_root>/models/geometry_estimation`.
- **Depth Generation** and **Image Generation** show whether the configured ComfyUI server is reachable and refresh that status automatically. Use **Check now** for an immediate check.
- Those generation tabs also offer a launcher selector and **Launch ComfyUI**. On Windows, the UI searches the configured ComfyUI folder and nearby parent folders for `run*.bat` or `*comfy*.bat` files, then starts the selected script in a separate console. Choose the GPU or CPU script that matches your installation. If no launcher is found, start ComfyUI manually.
- **Depth Generation** lets you select one image or a folder of images, choose where depth maps are saved, and open that output folder in your file explorer. Folder selection scans supported images recursively and preserves subfolders. Supported formats are PNG, JPG/JPEG, WEBP, and BMP.
- **Image Generation** loads the set names from `card_prompts/cards.yaml`. Select one or more sets in the scrollable list and start generation. The list is initially selected from `generate.local.yaml`. Edit the global positive and negative prompts between the LoRA presets and card-set list; use **Save prompts** to save them to the selected generation config. Starting image generation saves the prompt fields first.
- Image generation lets you choose one checkpoint and any run-level LoRA presets before selecting card sets; preset weights are combined with card-level LoRA references. Select **Empty preset (no LoRAs)** to disable LoRAs from both the selected presets and card/prompt data for that run.
- **Card Creation** provides a form and YAML editor for `cards.yaml` and the reusable character, outfit, pose, and place catalogs. The catalog forms let you add, edit, and remove entries with prompt, negative-prompt, display-name, and LoRA fields. The cards form lets you select catalog entries and a LoRA preset from dropdowns, edit shared set defaults or individual cards, and add card-specific positive and negative prompts. The YAML editor remains available for advanced fields and other prompt files. Save validates YAML and updates changed values in place, preserving existing comments and spacing; new keys are added alphabetically without reordering existing entries. Reload discards unsaved edits in the YAML editor.
- **LoRA Presets** lets you build and save named groups of LoRAs with independent model and CLIP strengths.
- **Local Models** is the last main tab and contains nested **LoRAs** and **Checkpoints** tabs. Installed model names are green and missing or unconfigured model names are red.
- The **Add Model** sub-tab registers an already-installed checkpoint or LoRA. Choose its file from inside the configured model folder, enter its catalog key, and provide any additional catalog fields as a YAML mapping. The app writes the entry to the corresponding workflow catalog and refreshes model status.
- Image Generation includes a button to open the configured image output folder.
- Use the theme toggle in the top-right corner to switch between dark and light mode.
- Tab pages include a vertical scrollbar when their contents extend beyond the visible area.
- Drag the divider above **Run output** to adjust the space shared by the active tab and output log. Editors and data lists expand to use the available tab height; the Local Models list/details divider can be dragged to adjust those panes independently.

Setup separates paths used by both generation types (the ComfyUI installation, output folder, and server URL) from paths needed only for image generation (checkpoint/LoRA folders, prompt aliases, and image output). Depth generation does not require the image-generation model folders.

In the Local Models tabs, select an item to see all fields from its YAML catalog entry. **Get it here** opens its `source` URL when present. **Put it here** opens the folder containing its configured model file, creating that folder if needed. Installed status checks whether the exact configured file exists. LoRA labels show the path beneath the configured LoRA directory without the `.safetensors` extension. Keep model `source` links and `file` paths maintained in `workflow/loras.yaml` and `workflow/checkpoints.yaml`.

New model entries store a path relative to the configured `loras_dir` or `checkpoints_dir`. The YAML metadata editor can include fields such as `source`, `base_model`, `prompt`, `trigger_words`, `default_weight`, and checkpoint `sampler_defaults`; the selected model file supplies `file`.

Generation progress and errors appear in the output panel. The image and depth workflows require ComfyUI to be running, with their required custom nodes and model files installed.

## Future ideas

- Add reliable ComfyUI workflow validation to check whether required custom nodes are installed.

## YAML data

The UI includes a YAML editor for the card prompt data files. The main catalogs are:

- `card_prompts/cards.yaml`: card sets and per-card prompt choices.
- `card_prompts/characters.yaml`, `outfits.yaml`, `poses.yaml`, and `places.yaml`: reusable prompt entries.
- `workflow/checkpoints.yaml` and `workflow/loras.yaml`: checkpoint and individual LoRA catalogs.
- `workflow/loras_preset.yaml`: reusable named LoRA presets. Cards can refer to these presets with `lora_preset`; image generation can also apply selected presets to every selected set.
- `generate.local.yaml`: generation settings and the initially selected sets.
- `paths.local.yaml`: machine-specific paths; do not share or commit this file.

Card references such as character, outfit, pose, place, checkpoint, and LoRA names must match entries in their respective catalogs. Optional `display_name` text at a card-set level in `cards.yaml` is shown beside the set key in the UI. A trailing comment on a set key (for example, `set_1: #rapunzel`) is also shown in the Image Generation set list when `display_name` is absent, and is retained when saving from the YAML editor. Put shared per-set card fields in `_defaults`; it stays at the top of its card set when saved. UI saves sort other YAML mapping keys alphabetically; list order is preserved. `paths.local.yaml` and `generate.local.yaml` are ignored by Git and created from their example files on first launch.

## Command-line validation

The UI uses `generation.py` to validate jobs and run workflows. It can also be run directly to inspect image-generation jobs without submitting them:

```sh
python generation.py --no-submit
```

Add `--skip-file-check` to skip local checkpoint and LoRA existence checks. For depth generation, pass an input file or folder explicitly:

```sh
python generation.py --mode depth_maps --depth-input "path\to\images" --depth-output "path\to\depths"
```

## Project layout

```text
card_prompts/       Card sets and reusable prompt entries
workflow/           Checkpoint/LoRA catalogs and ComfyUI workflow templates
depths/outputs/     Default destination for depth-generation results
output/             Default image-generation destination
run.py              Desktop UI entrypoint (python run.py)
ui/                 UI coordinator and feature modules
services/           YAML persistence and model-catalog path helpers
generation.py       Configuration, validation, and job creation
comfyui_workflow.py ComfyUI API submission and output collection
```
