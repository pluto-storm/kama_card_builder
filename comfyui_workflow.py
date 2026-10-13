"""Build ComfyUI API prompt files from resolved generation jobs."""

import json
import mimetypes
import re
import secrets
import shutil
import sys
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

DEPTH_OUTPUT_DIR = Path(__file__).resolve().parent / "depths" / "outputs"


class WorkflowError(Exception):
    pass


NODE_IDS = {
    "checkpoint": "4",
    "positive": "214",
    "negative": "215",
    "base_sampler": "10",
    "refine_sampler": "193",
    "save_image": "134",
    "save_depth": "232",
    "lora_loader": "247",
}


def _required_node(workflow, node_id, job_id):
    if node_id not in workflow:
        raise WorkflowError(f"{job_id}: workflow is missing node '{node_id}'")
    return workflow[node_id]


def _model_relative_path(path, model_dir, kind, job_id):
    try:
        return str(Path(path).resolve().relative_to(Path(model_dir).resolve()))
    except ValueError as error:
        raise WorkflowError(
            f"{job_id}: {kind} path '{path}' must be inside '{model_dir}'"
        ) from error


def _safe_component(value):
    component = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._")
    if not component:
        raise WorkflowError(f"Cannot use {value!r} in a ComfyUI filename prefix")
    return component


def _card_output_name(card_name):
    match = re.fullmatch(r"card_(\d+)", str(card_name))
    if not match:
        return _safe_component(card_name)
    return f"card_{int(match.group(1)):02d}"


def _output_category(card_name):
    if card_name == "card_0_icon":
        return "icons"
    if card_name == "card_0_poster":
        return "posters"
    return "cards"


def _card_stem(job):
    return f"{_safe_component(job['set'])}_{_card_output_name(job['card'])}"


def _generates_depth(job):
    """Only regular cards get a depth map; icons and posters do not."""
    return _output_category(job["card"]) == "cards"


def _prune_unreachable_nodes(workflow, output_ids):
    """Drop nodes that no remaining output node depends on."""
    reachable = set()
    pending = [node_id for node_id in output_ids if node_id in workflow]
    while pending:
        node_id = pending.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        for input_value in workflow[node_id].get("inputs", {}).values():
            if (
                isinstance(input_value, list)
                and input_value
                and isinstance(input_value[0], str)
                and input_value[0] in workflow
            ):
                pending.append(input_value[0])
    for node_id in list(workflow):
        if node_id not in reachable:
            del workflow[node_id]


def _image_stem(job):
    """Icons and posters are named after their set; cards keep the card number."""
    if _output_category(job["card"]) in ("icons", "posters"):
        return _safe_component(job["set"])
    return _card_stem(job)


def _reserve_run_directory(output_root):
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    while True:
        now = datetime.now()
        date_directory = output_root / now.strftime("%Y-%m-%d")
        date_directory.mkdir(parents=True, exist_ok=True)
        run_id = now.strftime("%H%M%S%f")
        reservation = date_directory / f".{run_id}.reserve"
        try:
            with reservation.open("x", encoding="ascii"):
                pass
        except FileExistsError:
            time.sleep(0.001)
            continue

        try:
            run_directory = date_directory / run_id
            run_directory.mkdir()
        except FileExistsError:
            reservation.unlink()
            time.sleep(0.001)
            continue

        reservation.unlink()
        for category in ("cards", "depth", "icons", "posters"):
            (run_directory / category).mkdir()
        return run_id, date_directory, run_directory


def _reserve_output_stem(base_stem, reserved_names):
    candidate = base_stem
    suffix = 2
    while candidate in reserved_names:
        candidate = f"{base_stem}_{suffix}"
        suffix += 1
    reserved_names.add(candidate)
    return candidate


def build_api_workflow(template, job, paths, run_id, date_name):
    """Return a ComfyUI API graph populated with one resolved job."""
    workflow = deepcopy(template)
    job_id = job["job_id"]

    checkpoint = _required_node(workflow, NODE_IDS["checkpoint"], job_id)
    checkpoint["inputs"]["ckpt_name"] = _model_relative_path(
        job["checkpoint"]["path"], paths["checkpoints_dir"], "checkpoint", job_id
    )
    _required_node(workflow, NODE_IDS["positive"], job_id)["inputs"]["positive"] = job[
        "positive"
    ]
    _required_node(workflow, NODE_IDS["negative"], job_id)["inputs"]["positive"] = job[
        "negative"
    ]

    base_sampler = _required_node(workflow, NODE_IDS["base_sampler"], job_id)["inputs"]
    refine_sampler = _required_node(workflow, NODE_IDS["refine_sampler"], job_id)["inputs"]
    base_sampler["noise_seed"] = int(job["seed"])
    refine_sampler["seed"] = int(job["seed"])

    settings = job.get("settings", {})
    setting_map = {
        "steps": "steps",
        "cfg": "cfg",
        "sampler": "sampler_name",
        "scheduler": "scheduler",
    }
    for setting, input_name in setting_map.items():
        if setting in settings:
            base_sampler[input_name] = settings[setting]
    if "steps" in settings and "end_at_step" in base_sampler:
        base_sampler["end_at_step"] = settings["steps"]

    image_size = job.get("image_size")
    if image_size is not None:
        _required_node(workflow, "235", job_id)["inputs"]["value"] = image_size[
            "width"
        ]
        _required_node(workflow, "234", job_id)["inputs"]["value"] = image_size[
            "height"
        ]

    if not re.fullmatch(r"\d{12}", run_id):
        raise WorkflowError(f"Invalid numeric run timestamp: {run_id!r}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_name):
        raise WorkflowError(f"Invalid output date directory: {date_name!r}")
    category = _output_category(job["card"])
    set_prefix = f"{date_name}/{run_id}/{category}/{_image_stem(job)}"
    _required_node(workflow, NODE_IDS["save_image"], job_id)["inputs"][
        "filename_prefix"
    ] = set_prefix
    _required_node(workflow, NODE_IDS["save_depth"], job_id)["inputs"][
        "filename_prefix"
    ] = f"{date_name}/{run_id}/depth/{_card_stem(job)}"
    if not _generates_depth(job):
        del workflow[NODE_IDS["save_depth"]]

    loader_id = NODE_IDS["lora_loader"]
    _required_node(workflow, loader_id, job_id)
    lora_source = NODE_IDS["checkpoint"]
    lora_nodes = {}
    for index, lora in enumerate(job.get("loras", [])):
        node_id = str(248 + index)
        lora_nodes[node_id] = {
            "inputs": {
                "lora_name": _model_relative_path(
                    lora["path"], paths["loras_dir"], "LoRA", job_id
                ),
                "strength_model": lora["weight"],
                "strength_clip": lora.get("clip", lora["weight"]),
                "model": [lora_source, 0],
                "clip": [lora_source, 1],
            },
            "class_type": "LoraLoader",
        }
        lora_source = node_id

    # Point every consumer of the workflow's placeholder loader at the final
    # checkpoint/LoRA node, then remove that UI-only loader.
    for node in workflow.values():
        for input_value in node.get("inputs", {}).values():
            if isinstance(input_value, list) and input_value and input_value[0] == loader_id:
                input_value[0] = lora_source
    del workflow[loader_id]
    workflow.update(lora_nodes)
    if not _generates_depth(job):
        _prune_unreachable_nodes(workflow, [NODE_IDS["save_image"]])
    return workflow


def build_depth_api_workflow(template, job, comfyui_image, run_id, date_name):
    """Return the depth-only ComfyUI graph populated with one uploaded image."""
    workflow = deepcopy(template)
    job_id = job["job_id"]
    if not re.fullmatch(r"\d{12}", run_id):
        raise WorkflowError(f"Invalid numeric run timestamp: {run_id!r}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_name):
        raise WorkflowError(f"Invalid output date directory: {date_name!r}")

    _required_node(workflow, "251", job_id)["inputs"]["image"] = comfyui_image
    set_name = job.get("comfyui_set_name")
    if not set_name:
        set_label = job.get("set")
        set_name = f"{run_id}_{_safe_component(set_label or 'root')}"
    set_prefix = f"{date_name}/{_safe_component(set_name)}"
    _required_node(workflow, NODE_IDS["save_depth"], job_id)["inputs"][
        "filename_prefix"
    ] = f"{set_prefix}/{_safe_component(job['card'])}"
    return workflow


def _request_json(url, payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"} if body else {},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise WorkflowError(
            f"ComfyUI returned HTTP {error.code} for {url}: {detail}"
        ) from error
    except (URLError, TimeoutError) as error:
        raise WorkflowError(f"Could not reach ComfyUI at {url}: {error}") from error
    except json.JSONDecodeError as error:
        raise WorkflowError(f"ComfyUI returned invalid JSON for {url}: {error}") from error


def _upload_input_image(image_path, base_url, subfolder):
    image_path = Path(image_path)
    boundary = f"----KamaCardBuilder{secrets.token_hex(16)}"
    fields = {
        "type": "input",
        "subfolder": subfolder,
        "overwrite": "false",
    }
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("ascii"))
        body.extend(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode(
                "utf-8"
            )
        )

    content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    safe_filename = image_path.name.replace('"', "")
    body.extend(f"--{boundary}\r\n".encode("ascii"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="image"; filename="{safe_filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    with image_path.open("rb") as image_file:
        body.extend(image_file.read())
    body.extend(f"\r\n--{boundary}--\r\n".encode("ascii"))

    request = Request(
        f"{base_url.rstrip('/')}/upload/image",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise WorkflowError(
            f"ComfyUI returned HTTP {error.code} uploading {image_path}: {detail}"
        ) from error
    except (URLError, TimeoutError) as error:
        raise WorkflowError(f"Could not upload {image_path} to ComfyUI: {error}") from error
    except json.JSONDecodeError as error:
        raise WorkflowError(f"ComfyUI returned invalid upload JSON: {error}") from error

    name = result.get("name")
    if not name:
        raise WorkflowError(f"ComfyUI did not return an uploaded image name: {result}")
    uploaded_subfolder = result.get("subfolder", "").strip("/\\")
    return f"{uploaded_subfolder}/{name}" if uploaded_subfolder else name


def _move_completed_image(
    image,
    output_root,
    comfyui_output_root,
    date_name,
    set_name,
    filename,
    *,
    expected_subfolder=None,
    destination_path=None,
):
    if image.get("type") != "output":
        raise WorkflowError(f"Expected a ComfyUI output image, got {image!r}")

    subfolder_parts = [
        part for part in re.split(r"[\\/]", image.get("subfolder", "")) if part
    ]
    expected_parts = expected_subfolder or [date_name, f"{set_name}"]
    if subfolder_parts != expected_parts:
        raise WorkflowError(
            f"Unexpected ComfyUI output folder: {image.get('subfolder')!r}"
        )

    source_root = Path(comfyui_output_root).resolve()
    source_path = source_root.joinpath(*subfolder_parts, image.get("filename", ""))
    try:
        source_path.resolve().relative_to(source_root)
    except ValueError as error:
        raise WorkflowError(f"ComfyUI returned an unsafe output path: {source_path}") from error
    if not source_path.is_file():
        raise WorkflowError(f"ComfyUI output file not found: {source_path}")

    if destination_path is None:
        destination_directory = Path(output_root) / date_name / set_name
        destination_directory.mkdir(parents=True, exist_ok=True)
        destination = destination_directory / filename
    else:
        output_root = Path(output_root).resolve()
        destination = Path(destination_path)
        try:
            destination.resolve().relative_to(output_root)
        except ValueError as error:
            raise WorkflowError(
                f"Depth output path is outside '{output_root}': {destination}"
            ) from error
        destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with destination.open("xb") as target:
            created = True
            with source_path.open("rb") as source:
                shutil.copyfileobj(source, target)
    except FileExistsError as error:
        raise WorkflowError(f"Refusing to overwrite existing image: {destination}") from error
    except OSError as error:
        if created:
            destination.unlink(missing_ok=True)
        raise WorkflowError(f"Could not move ComfyUI image to {destination}: {error}") from error

    retry_delays = (0.1, 0.25, 0.5, 1)
    for attempt in range(len(retry_delays) + 1):
        try:
            source_path.unlink()
            break
        except FileNotFoundError:
            break
        except PermissionError as error:
            if attempt == len(retry_delays):
                print(
                    "WARNING: Image was saved successfully, but could not remove "
                    f"the ComfyUI source file because it is still in use: "
                    f"{source_path} ({error})",
                    file=sys.stderr,
                    flush=True,
                )
                break
            time.sleep(retry_delays[attempt])
    return destination


def _save_completed_images(
    job,
    prompt_history,
    output_root,
    comfyui_output_root,
    date_name,
    run_id,
    image_stem,
    depth_stem,
):
    outputs = prompt_history.get("outputs", {})
    saved_paths = []
    expected_outputs = [
        (NODE_IDS["save_image"], (_output_category(job["card"]),), image_stem),
    ]
    if depth_stem is not None:
        expected_outputs.append((NODE_IDS["save_depth"], ("depth",), depth_stem))
    for node_id, relative_directory, filename_stem in expected_outputs:
        images = outputs.get(node_id, {}).get("images", [])
        if not images:
            raise WorkflowError(
                f"ComfyUI completed {job['job_id']} without image output from node {node_id}"
            )

        for image_index, image in enumerate(images, start=1):
            index_suffix = f"_{image_index}" if len(images) > 1 else ""
            filename = f"{filename_stem}{index_suffix}.png"
            destination = Path(output_root).joinpath(
                date_name, run_id, *relative_directory, filename
            )
            image_path = _move_completed_image(
                image,
                output_root,
                comfyui_output_root,
                date_name,
                run_id,
                filename,
                expected_subfolder=[date_name, run_id, *relative_directory],
                destination_path=destination,
            )
            saved_paths.append(image_path)

    output_directory = Path(output_root) / date_name / run_id
    return output_directory, saved_paths


def submit_api_workflows(jobs, template, paths, comfyui_url):
    """Build each prompt in memory, submit it, and wait for completion."""
    if not comfyui_url:
        raise WorkflowError("paths.local.yaml must define 'comfyui_url' to generate images")

    base_url = comfyui_url.rstrip("/")
    run_id, date_directory, run_directory = _reserve_run_directory(paths["output_dir"])
    date_name = date_directory.name
    comfyui_output_root = paths.get(
        "comfyui_output_dir", Path(paths["comfyui_root"]) / "output"
    )
    print(f"Run output: {run_directory}", flush=True)
    card_counts = {}
    for job in jobs:
        card_key = (job["set"], job["card"])
        card_counts[card_key] = card_counts.get(card_key, 0) + 1
    reserved_names = set()

    for index, job in enumerate(jobs, start=1):
        workflow = build_api_workflow(template, job, paths, run_id, date_name)

        print(f"Submitting {index}/{len(jobs)}: {job['job_id']}", flush=True)
        result = _request_json(f"{base_url}/prompt", {"prompt": workflow})
        if result.get("node_errors"):
            raise WorkflowError(
                f"ComfyUI rejected {job['job_id']}: {json.dumps(result['node_errors'])}"
            )
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise WorkflowError(
                f"ComfyUI did not return a prompt_id for {job['job_id']}: {result}"
            )

        started_at = time.monotonic()
        history_url = f"{base_url}/history/{quote(str(prompt_id))}"
        while time.monotonic() - started_at < 3600:
            history = _request_json(history_url)
            prompt_history = history.get(str(prompt_id))
            if prompt_history:
                status = prompt_history.get("status", {})
                if status.get("completed"):
                    if status.get("status_str") != "success":
                        raise WorkflowError(
                            f"ComfyUI failed {job['job_id']}: {json.dumps(status)}"
                        )
                    seed_suffix = ""
                    if card_counts[(job["set"], job["card"])] > 1:
                        seed_suffix = f"_seed{_safe_component(job['seed'])}"
                    category = _output_category(job["card"])
                    image_stem = _reserve_output_stem(
                        f"{category}/{_image_stem(job)}{seed_suffix}",
                        reserved_names,
                    ).split("/", 1)[1]
                    depth_stem = None
                    if _generates_depth(job):
                        depth_stem = _reserve_output_stem(
                            f"depth/{_card_stem(job)}{seed_suffix}", reserved_names
                        ).split("/", 1)[1]
                    destination, saved_paths = _save_completed_images(
                        job,
                        prompt_history,
                        paths["output_dir"],
                        comfyui_output_root,
                        date_name,
                        run_id,
                        image_stem,
                        depth_stem,
                    )
                    print(f"Completed {index}/{len(jobs)}: {job['job_id']}", flush=True)
                    print(f"Saved images to {destination}: {', '.join(p.name for p in saved_paths)}", flush=True)
                    break
            time.sleep(2)
        else:
            raise WorkflowError(
                f"Timed out waiting for ComfyUI to finish {job['job_id']}"
            )

    comfyui_run_directory = Path(comfyui_output_root) / date_name / run_id
    for category in ("cards", "depth", "icons", "posters"):
        try:
            (comfyui_run_directory / category).rmdir()
        except OSError:
            pass
    try:
        comfyui_run_directory.rmdir()
    except OSError:
        pass


def _save_completed_depth(
    job, prompt_history, output_root, comfyui_output_root, date_name, set_name
):
    images = prompt_history.get("outputs", {}).get(NODE_IDS["save_depth"], {}).get(
        "images", []
    )
    if not images:
        raise WorkflowError(
            f"ComfyUI completed {job['job_id']} without depth output from node "
            f"{NODE_IDS['save_depth']}"
        )

    saved_paths = []
    for image_index, image in enumerate(images, start=1):
        destination = Path(job["output_path"])
        if len(images) > 1:
            destination = destination.with_name(
                f"{destination.stem}_{image_index}{destination.suffix}"
            )
        saved_paths.append(
            _move_completed_image(
                image,
                output_root,
                comfyui_output_root,
                date_name,
                set_name,
                destination.name,
                expected_subfolder=[date_name, set_name],
                destination_path=destination,
            )
        )
    return saved_paths[0].parent, saved_paths


def submit_depth_api_workflows(jobs, template, paths, comfyui_url):
    """Upload source images and run the depth-only graph for each one."""
    if not comfyui_url:
        raise WorkflowError("paths.local.yaml must define 'comfyui_url' to generate depth maps")

    base_url = comfyui_url.rstrip("/")
    now = datetime.now()
    run_id = now.strftime("%H%M%S%f")
    date_name = now.strftime("%Y-%m-%d")
    comfyui_output_root = paths.get(
        "comfyui_output_dir", Path(paths["comfyui_root"]) / "output"
    )
    depth_output_dir = Path(paths.get("depth_output_dir", DEPTH_OUTPUT_DIR))
    print(f"Depth outputs: {depth_output_dir}", flush=True)
    reserved_names = set()

    for index, job in enumerate(jobs, start=1):
        set_name = f"{run_id}_{index:04d}"
        job["comfyui_set_name"] = set_name
        upload_subfolder = f"kama_card_builder/{run_id}_{index:04d}"
        comfyui_image = _upload_input_image(job["input_path"], base_url, upload_subfolder)
        workflow = build_depth_api_workflow(
            template, job, comfyui_image, run_id, date_name
        )

        print(f"Submitting depth map {index}/{len(jobs)}: {job['job_id']}", flush=True)
        result = _request_json(f"{base_url}/prompt", {"prompt": workflow})
        if result.get("node_errors"):
            raise WorkflowError(
                f"ComfyUI rejected {job['job_id']}: {json.dumps(result['node_errors'])}"
            )
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise WorkflowError(
                f"ComfyUI did not return a prompt_id for {job['job_id']}: {result}"
            )

        started_at = time.monotonic()
        history_url = f"{base_url}/history/{quote(str(prompt_id))}"
        while time.monotonic() - started_at < 3600:
            history = _request_json(history_url)
            prompt_history = history.get(str(prompt_id))
            if prompt_history:
                status = prompt_history.get("status", {})
                if status.get("completed"):
                    if status.get("status_str") != "success":
                        raise WorkflowError(
                            f"ComfyUI failed {job['job_id']}: {json.dumps(status)}"
                        )
                    if job["output_path"] in reserved_names:
                        raise WorkflowError(
                            f"Multiple inputs map to the same depth output: {job['output_path']}"
                        )
                    reserved_names.add(job["output_path"])
                    destination, saved_paths = _save_completed_depth(
                        job,
                        prompt_history,
                        depth_output_dir,
                        comfyui_output_root,
                        date_name,
                        set_name,
                    )
                    print(f"Completed depth map {index}/{len(jobs)}: {job['job_id']}", flush=True)
                    print(f"Saved depth map to {destination}: {', '.join(p.name for p in saved_paths)}", flush=True)
                    break
            time.sleep(2)
        else:
            raise WorkflowError(
                f"Timed out waiting for ComfyUI to finish {job['job_id']}"
            )


def main():
    try:
        payload = json.load(sys.stdin)
        if payload.get("submit", True):
            with open(payload["template_path"], encoding="utf-8") as file:
                template = json.load(file)
            submitter = (
                submit_depth_api_workflows
                if payload.get("mode") == "depth_maps"
                else submit_api_workflows
            )
            submitter(
                payload["jobs"], template, payload["paths"], payload["paths"].get("comfyui_url")
            )
        else:
            print("Submission disabled; no ComfyUI jobs were submitted.")
    except (KeyError, OSError, json.JSONDecodeError, WorkflowError) as error:
        print(f"ERROR: ComfyUI generation failed: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())