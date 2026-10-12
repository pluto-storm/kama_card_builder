# Kama Card Builder

This project keeps card and character data in YAML and uses ComfyUI to generate images. There are two roles:

- **Data contributors** add or improve card, character, and LoRA entries. They do not need ComfyUI, model files, or a GPU.
- **The generation operator** maintains a working ComfyUI installation, checks contributions, runs the workflows, and shares the finished images.

The generation program has two modes:

- `generate_images` builds images from your card prompts and also saves a depth image for each generated image.
- `depth_maps` takes existing images from `depths/inputs` and saves depth maps under `depths/outputs`, preserving nested folders.

The normal image workflow creates files under the `output` folder. The depth-only workflow does not need card prompts, checkpoints, or LoRAs, but it does need ComfyUI and the depth workflow's custom nodes and model.

## How the Code Works

`run.py` is the entry point. It starts by reading `paths.local.yaml` for machine-specific folders and the ComfyUI address, then reads the selected generation config (by default, `generate.local.yaml`) to decide what kind of work to run.

In `generate_images` mode, `run.py` loads the card sets and prompt dictionaries from `card_prompts/`, plus the checkpoint and LoRA catalogs from `workflow/`. It checks that the selected set, character, outfit, pose, place, checkpoint, and LoRA names refer to known entries. For every selected card and seed, it combines the global, category, and card-level prompt text, resolves the LoRA files and weights, and builds a complete job. Character, outfit, pose, and place prompts are combined in that order; card-specific prompt and LoRA choices can add or override details.

The runner then passes those resolved jobs to `comfyui_workflow.py`. That helper fills the `workflow/image_gen_w_depth.json` API graph with each job's prompt, checkpoint, seed, dimensions, sampler settings, and LoRAs; submits it to ComfyUI; waits for completion; and moves the generated image and depth image into the configured output folder.

In `depth_maps` mode, `run.py` skips the card and model catalogs. It finds supported images recursively in `depths/inputs`, and `comfyui_workflow.py` uploads each one to ComfyUI and runs `workflow/image_gen_depth.json`. The resulting depth image is saved under `depths/outputs` with the same relative folder and filename stem.

## Why the Data Is Split This Way

The YAML files keep reusable content separate from the code that runs it. A character can be defined once and reused by many cards; outfits, poses, places, and LoRAs work the same way. Card sets then combine those pieces instead of copying the same prompt text into every card.

This structure makes contributions smaller and combinations easier to review. Someone can add a character or a set without changing Python or needing ComfyUI. Shared entries can be refined once and improve every card that uses them. Machine-specific paths stay in ignored local config files, while the shared catalogs describe names and reusable content that can move between contributors' computers.

## Contribute YAML Without ComfyUI

You can contribute using a text editor and GitHub (or the project's usual file-sharing process). You do not need to install Python or ComfyUI just to edit these data files.

The main files to contribute to are:

- `card_prompts/characters.yaml`: reusable character descriptions, display names, and optional LoRA references.
- `card_prompts/cards.yaml`: card sets that combine characters, outfits, poses, and places.
- `workflow/loras.yaml`: LoRA names, filenames, trigger words, optional compatibility information, and reusable LoRA presets.
- `card_prompts/outfits.yaml`, `poses.yaml`, and `places.yaml`: reusable prompt pieces referenced by cards.

Keep independent named entries alphabetically sorted where practical so contributors can scan the files and spot duplicates. In `cards.yaml`, keep `set_defaults` at the top of each set. Do not reorder lists whose order is meaningful, such as `sets_to_generate`, seeds, or LoRA references.

### Add a Character

Add a unique key to `characters.yaml`. The key is the name cards use to refer to the character. A prompt is recommended; `default_display` and `lora` are optional.

```yaml
new_character:
  prompt: short visual description of the character
  default_display: "NEW CHARACTER"
  lora:
    - new_character_lora
```

Only include `lora` when that exact LoRA key also exists in `workflow/loras.yaml`. Otherwise, leave the `lora` section out; the generation operator can still test the character prompt without a character LoRA.

### Add Cards

Add a uniquely named set to `cards.yaml`. Every value such as `character`, `outfit`, `pose`, and `place` must match a key in the corresponding YAML file. `set_defaults` applies to every card unless a card overrides a field.

```yaml
new_set:
  set_defaults:
    character: new_character
  card_1:
    outfit: existing_outfit_key
    pose: existing_pose_key
    place: existing_place_key
    prompt_pos: optional extra prompt details
```

Cards also support `prompt_neg`, `loras`, and `lora_preset`. Use the existing entries as examples, and do not rename a key that another card already uses without updating those references too.

### Add or Update a LoRA Entry

LoRA keys are exact names used by character, outfit, pose, place, and card entries. Give the entry the exact `.safetensors` filename and a path alias the generation operator has configured in `paths.local.yaml`.

```yaml
new_character_lora:
  file: ${characters}/new_character.safetensors
  base_model: pony
  trigger_words:
    - new_character
  default_weight: 0.8
```

`base_model`, `trigger_words`, and `default_weight` are optional. Do not add your computer's absolute path or edit `paths.local.yaml`; that file is private to each machine. If you do not know the final LoRA filename or folder, include the LoRA name and source/details in your contribution notes and let the generation operator fill in the machine-specific mapping.

### Send a Contribution

If you are familiar with GitHub, create a branch (or fork), edit the relevant YAML files, and submit a pull request. If you are not familiar with Git or GitHub, send the edited YAML file or files directly to the project owner, who can review and add them. Either way, include a short note describing the contribution and any required LoRA file or source. Do not send `*.local.yaml`, generated images, model files, or personal paths.

A contribution does not need to include a generated image. The generation operator can review the data, run accepted contributions later, and share the finished images when they are available.

Python validation is optional for data contributors. If Python is already installed, copy the example local configs if needed, set `mode: generate_images` in `generate.local.yaml`, and set `sets_to_generate` to the set you added. Then run:

```sh
python -m pip install -r requirements.txt
python run.py --no-submit --skip-file-check
```

This builds and validates the jobs without contacting ComfyUI or checking whether checkpoint/LoRA files exist on your computer. The local config must still name a checkpoint entry that exists in `workflow/checkpoints.yaml`. The generation operator will perform the full asset check and ComfyUI run before sharing images.

## For the Generation Operator

Only the person running image or depth generation needs the setup below.

## Before You Start

You need:

- Windows, macOS, or Linux
- Python 3.10 or newer
- ComfyUI installed and running on the computer that will process the images
- The model files and ComfyUI custom nodes required by the selected workflow

This project's Python requirements install only its YAML reader. They do not install ComfyUI, model weights, LoRAs, or ComfyUI custom nodes. Install and test those in ComfyUI first. Keep ComfyUI running while this project submits work to it.

## 1. Install the Python Requirements

Open a terminal in this project folder. On Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks environment activation, run this in the same terminal and try activating again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

On macOS or Linux, use:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The virtual environment keeps this project's Python packages separate from other projects. Activate it each time you open a new terminal for this project.

## 2. Create Your Local Configuration

The `*.example.yaml` files are templates. Create local copies only if they do not already exist. Do not replace an existing local file; it may contain machine-specific settings.

Windows PowerShell:

```powershell
if (-not (Test-Path paths.local.yaml)) { Copy-Item paths.example.yaml paths.local.yaml }
if (-not (Test-Path generate.local.yaml)) { Copy-Item generate.example.yaml generate.local.yaml }
```

macOS or Linux:

```sh
[ -f paths.local.yaml ] || cp paths.example.yaml paths.local.yaml
[ -f generate.local.yaml ] || cp generate.example.yaml generate.local.yaml
```

Files ending in `.local.yaml` are ignored by Git because they usually contain personal paths and settings.

## 3. Set Up `paths.local.yaml`

Edit `paths.local.yaml` and replace the example paths with the paths on your computer. The example below is for Windows; use forward slashes in YAML paths, including on Windows. On macOS/Linux, set `comfyui_root` to your ComfyUI folder, such as `/home/you/ComfyUI`.

```yaml
comfyui_root: 'W:/AI/ComfyUI'
checkpoints_dir: ${comfyui_root}/models/checkpoints
loras_dir: ${comfyui_root}/models/loras
comfyui_output_dir: ${comfyui_root}/output
output_dir: ./output
comfyui_url: http://127.0.0.1:8188

enhancements: ${loras_dir}/enhancements
styles: ${loras_dir}/styles
characters: ${loras_dir}/characters
outfits: ${loras_dir}/outfits
poses: ${loras_dir}/poses
body: ${loras_dir}/body
```

Change `comfyui_root` to the ComfyUI folder on your machine. The `checkpoints_dir`, `loras_dir`, and `comfyui_output_dir` values above are based on the usual ComfyUI folder layout. Change them if yours is different. The category paths such as `styles` and `characters` are used by the LoRA catalog to locate files in your LoRA folders.

Keep `comfyui_url` set to the address ComfyUI uses. If you run ComfyUI on another computer, use that computer's reachable address instead of `127.0.0.1`.

## 4. Add Checkpoints and LoRAs

For image generation, the name in `checkpoint_to_use` must match an entry in `workflow/checkpoints.yaml`. That entry's `file` must identify an installed checkpoint under `checkpoints_dir`.

Every LoRA referenced by a character, outfit, pose, place, card, or preset must have an entry in `workflow/loras.yaml`. Its `file` must point to an installed LoRA under `loras_dir`. Presets are groups of LoRA names defined under `lora_presets` in that same file. A preset LoRA can specify `weight` for model strength and optional `clip` for CLIP strength; when `clip` is omitted, it defaults to `weight`.

Example checkpoint entry:

```yaml
my_checkpoint:
  name: My Checkpoint
  file: my_checkpoint.safetensors
  base_model: pony
  sampler_defaults:
    steps: 30
    cfg: 7
    sampler: dpmpp_2m
    scheduler: karras
```

The `base_model` value helps catch incompatible checkpoint and LoRA combinations. Check that every model filename and folder matches the files installed in ComfyUI.

## 5. Define Cards and Choose a Run

The files in `card_prompts` are reusable dictionaries:

- `characters.yaml`, `outfits.yaml`, `poses.yaml`, and `places.yaml` describe prompt entries and optional LoRAs.
- `cards.yaml` combines those entries into named sets.

For example, a card set can use shared defaults and override them on individual cards:

```yaml
my_set:
  set_defaults:
    character: kim_possible
  card_1:
    outfit: kim_possible_student
    pose: thinking
    place: school
  card_2:
    outfit: kim_possible_spy
    pose: proud
    place: city
```

The names on the right must already exist in the corresponding prompt YAML files. A card can also use `prompt_pos`, `prompt_neg`, `loras`, or `lora_preset`. Per-card values override `set_defaults`.

For image generation, edit `generate.local.yaml`:

```yaml
mode: generate_images
checkpoint_to_use: pony
image_size:
  width: 1024
  height: 1024
sets_to_generate:
  - my_set
global_positive: best quality
global_negative: low quality, blurry
```

`checkpoint_to_use` must match a checkpoint entry. Each name under `sets_to_generate` must match a set in `card_prompts/cards.yaml`. You can list more than one set.

To generate depth maps for existing images instead, set:

```yaml
mode: depth_maps
```

Then put images in `depths/inputs`. Subfolders are supported. The runner processes PNG, JPG/JPEG, WEBP, and BMP files recursively and mirrors their folder locations under `depths/outputs`. For example, `depths/inputs/people/kim/pose.jpg` becomes `depths/outputs/people/kim/pose.png`. If two source files have the same name but different extensions, the output names include the source extension to keep them unique.

## 6. Run the Project

### Install the ComfyUI Nodes

Do this once for each workflow you plan to run:

- Image generation: `workflow/image_gen_w_depth.json`
- Depth maps only: `workflow/image_gen_depth.json`

Start ComfyUI and open its web page. Load the matching workflow, open ComfyUI Manager, and choose **Install Missing Custom Nodes**. Install the missing node packages Manager lists, restart ComfyUI, then repeat the scan if needed. The image-generation workflow uses additional nodes beyond the depth workflow, so check both if you plan to use both modes.

ComfyUI Manager installs node extensions, not model weights. The checkpoint, LoRA, and Depth Anything model files must still be installed in the locations expected by your ComfyUI setup.

**Workflow file note:** the JSON files in this repository are API prompt graphs used by `run.py`; they are not standard visual canvas exports. Depending on your ComfyUI version, the canvas may not load them for Manager's automatic scan. If that happens, get the corresponding visual workflow JSON and load that into the canvas for the missing-node scan. Keep the API JSON files in this repository unchanged; `run.py` needs them in API format.

After the required nodes and models are installed, keep ComfyUI running and run the following commands from the project folder with the virtual environment activated.

First, check the jobs without submitting them to ComfyUI:

```sh
python run.py --no-submit
```

Review the mode and the inputs/outputs printed in the summary. If the configuration looks right, submit the jobs:

```sh
python run.py
```

Useful options:

```sh
python run.py --verbose              # show every job
python run.py --skip-file-check      # skip local checkpoint/LoRA file checks
python run.py --generate other.yaml  # use another generation config in this folder
python run.py --json jobs.json       # save the resolved job list as JSON
```

`--skip-file-check` is for special cases; it does not install or load missing models. `--no-submit` still checks and lists jobs, but does not queue them in ComfyUI.

## Where Results Go

Image-generation runs create a new dated, timestamped folder under the configured `output_dir`. Each card's generated image is saved there, and its same-named depth map is saved in that folder's `depths` subfolder.

Depth-only runs save maps under `depths/outputs`, keeping the input folder structure and filename stem. The original input images are not changed. If an output file already exists, the runner will not overwrite it; move or rename the existing output before retrying that image.

## Still in Progress
- Make body data type so that each character can have different body types defined and easily switch 
- Refine and organize the prompt wording in the character, outfit, pose, and place catalogs.
- Build out more complete and varied card sets using the reusable catalog entries.
- Improve pose options and make their descriptions more consistent and useful across characters.
- Review LoRA names, source links, trigger words, weights, and model compatibility as the catalog grows.
- Generate and review batches of contributed sets, then share selected results with contributors.

## Troubleshooting

- **`Missing file: paths.local.yaml` or `generate.local.yaml`:** copy the matching example file to its local filename.
- **Checkpoint or LoRA file not found:** check its `file` entry and the matching directory in `paths.local.yaml`.
- **Unknown card, pose, outfit, place, or LoRA:** check spelling and confirm the key exists in its YAML catalog.
- **The example image run reports unknown `raven` or `starfire`:** the current `cards.yaml` uses those character keys, but `characters.yaml` does not define them. Add the intended entries or change those card references before running image generation.
- **ComfyUI connection error:** start ComfyUI and confirm `comfyui_url` is correct and reachable.
- **ComfyUI reports missing nodes or models:** install the custom nodes and model files required by the selected workflow in ComfyUI, then restart it.
- **Depth mode finds no images:** put supported image files under `depths/inputs`; nested folders are scanned automatically.

## Project Files

```text
card_prompts/       Card sets and reusable prompt entries
workflow/           Checkpoint/LoRA catalogs and ComfyUI workflow templates
depths/inputs/      Existing images for depth-only runs
depths/outputs/     Depth maps created from depths/inputs
output/             Images and depth maps from image-generation runs
run.py              Configuration, validation, and job creation
comfyui_workflow.py ComfyUI API submission and output collection
```