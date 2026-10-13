"""Setup page and configuration editing."""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import generation
from services.config_store import _write_sorted_yaml
from ui.constants import PATHS_FILE, ROOT


class SetupMixin:
    def _build_setup_page(self, page):
        ttk.Label(
            page,
            text=(
                "Depth generation only needs the shared ComfyUI settings below. "
                "Checkpoint, LoRA, and image-output paths are only needed for image generation."
            ),
            wraplength=760,
        ).pack(anchor="w", pady=(0, 10))

        self.shared_path_frame = ttk.LabelFrame(
            page, text="Required for depth and image generation", padding=8
        )
        self.shared_path_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(
            self.shared_path_frame,
            text="ComfyUI must be running and its URL reachable for either workflow.",
            wraplength=700,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

        self.image_path_frame = ttk.LabelFrame(
            page, text="Image generation only", padding=8
        )
        self.image_path_frame.pack(fill="x")
        ttk.Label(
            self.image_path_frame,
            text="Depth-only runs do not require these model folders or the image output path.",
            wraplength=700,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

        controls = ttk.Frame(page)
        controls.pack(anchor="w", pady=(10, 0))
        ttk.Button(controls, text="Reload", command=self._load_paths).pack(side="left")
        ttk.Button(controls, text="Save paths", command=self._save_paths).pack(
            side="left", padx=(8, 0)
        )

    def _path_summary(self, parent, keys):
        frame = ttk.LabelFrame(parent, text="Configured paths")
        frame.pack(fill="x", pady=(4, 0))
        for row, key in enumerate(keys):
            ttk.Label(frame, text=f"{key}:").grid(
                row=row, column=0, sticky="w", padx=8, pady=4
            )
            label = ttk.Label(frame, text="", wraplength=650)
            label.grid(row=row, column=1, sticky="w", padx=8, pady=4)
            self.path_entries.setdefault("_summaries", {}).setdefault(key, []).append(label)
        frame.columnconfigure(1, weight=1)

    def _load_paths(self):
        try:
            config = generation.load_yaml(PATHS_FILE)
        except (generation.ConfigError, OSError) as error:
            if PATHS_FILE.exists():
                messagebox.showerror("Could not load paths", str(error))
                return
            try:
                config = generation.load_yaml(ROOT / "paths.example.yaml")
            except (generation.ConfigError, OSError) as example_error:
                messagebox.showerror("Could not load paths", str(example_error))
                return

        config.pop("depth_input_dir", None)
        config.pop("depth_output_dir", None)
        config.pop("ge_dir", None)
        ge_model = config.get("ge_model")
        if isinstance(ge_model, str) and ge_model.startswith("${ge_dir}"):
            config["ge_model"] = (
                "${comfyui_root}/models/geometry_estimation"
                + ge_model[len("${ge_dir}"):]
            )
        config.setdefault(
            "ge_model",
            "${comfyui_root}/models/geometry_estimation/"
            "depth_anything_3_mono_large.safetensors",
        )
        self.path_entries = {"_summaries": self.path_entries.get("_summaries", {})}
        shared_keys = {
            "comfyui_root",
            "comfyui_output_dir",
            "comfyui_url",
            "ge_model",
        }
        self._render_path_group(
            self.shared_path_frame, config, shared_keys, description_row=0
        )
        self._render_path_group(
            self.image_path_frame,
            config,
            set(config) - shared_keys,
            description_row=0,
        )
        self._update_summaries()
        for kind in ("loras", "checkpoints"):
            self._load_asset_catalog(kind, show_errors=False)
        self._find_comfyui_launchers(show_errors=False)

    def _render_path_group(self, frame, config, keys, description_row):
        for child in frame.grid_slaves():
            info = child.grid_info()
            if int(info["row"]) > description_row:
                child.destroy()
        row = description_row + 1
        for key, value in config.items():
            if key not in keys:
                continue
            label = "Geometry Estimation" if key == "ge_model" else f"{key}:"
            ttk.Label(frame, text=label).grid(
                row=row, column=0, sticky="w", padx=(0, 8), pady=4
            )
            variable = tk.StringVar(value=str(value))
            ttk.Entry(frame, textvariable=variable).grid(
                row=row, column=1, sticky="ew", pady=4
            )
            self.path_entries[key] = variable
            if key == "ge_model":
                ttk.Button(
                    frame,
                    text="Browse...",
                    command=lambda var=variable: self._browse_ge_model(var),
                ).grid(row=row, column=2, padx=(8, 0), pady=4)
            elif key.endswith(("_dir", "_root")) and key not in {
                "checkpoints_dir",
                "loras_dir",
            }:
                ttk.Button(
                    frame,
                    text="Browse...",
                    command=lambda var=variable: self._browse_directory(var),
                ).grid(row=row, column=2, padx=(8, 0), pady=4)
            row += 1
        frame.columnconfigure(1, weight=1)

    def _raw_ui_paths(self):
        raw = {
            key: variable.get().strip()
            for key, variable in self.path_entries.items()
            if not key.startswith("_")
        }
        if not raw:
            source = PATHS_FILE if PATHS_FILE.exists() else ROOT / "paths.example.yaml"
            raw = generation.load_yaml(source)
        return raw

    def _save_paths(self, show_confirmation=True):
        values = {
            key: variable.get().strip()
            for key, variable in self.path_entries.items()
            if not key.startswith("_")
        }
        if any(not value for value in values.values()):
            messagebox.showerror("Invalid paths", "Path values cannot be empty.")
            return False
        try:
            _write_sorted_yaml(PATHS_FILE, values)
        except OSError as error:
            messagebox.showerror("Could not save paths", str(error))
            return False
        self._update_summaries()
        for kind in ("loras", "checkpoints"):
            self._load_asset_catalog(kind, show_errors=False)
        self._find_comfyui_launchers(show_errors=False)
        self._refresh_comfyui()
        if show_confirmation:
            messagebox.showinfo("Paths saved", f"Saved path settings to {PATHS_FILE}")
        return True

    def _update_summaries(self):
        summaries = self.path_entries.get("_summaries", {})
        for key, labels in summaries.items():
            value = self.path_entries.get(key)
            text = value.get() if value else "(not configured)"
            for label in labels:
                label.configure(text=text)

    def _browse_directory(self, variable):
        initial_dir = Path(variable.get()).expanduser()
        if not initial_dir.is_dir():
            initial_dir = ROOT
        selected = filedialog.askdirectory(initialdir=str(initial_dir))
        if selected:
            variable.set(selected)
            self._update_summaries()

    def _browse_ge_model(self, variable):
        try:
            raw_paths = self._raw_ui_paths()
            comfyui_root = Path(
                generation.expand_vars(
                    raw_paths.get("comfyui_root", ""),
                    raw_paths,
                    label="paths.local.yaml 'comfyui_root'",
                )
            ).expanduser()
            if not comfyui_root.is_absolute():
                comfyui_root = ROOT / comfyui_root
            initial_dir = comfyui_root / "models" / "geometry_estimation"
        except (generation.ConfigError, OSError, ValueError):
            initial_dir = ROOT
        current_model = Path(variable.get()).expanduser()
        if current_model.parent.is_dir():
            initial_dir = current_model.parent
        elif not initial_dir.is_dir():
            initial_dir = ROOT
        selected = filedialog.askopenfilename(
            initialdir=str(initial_dir),
            filetypes=(("Model files", "*.safetensors *.ckpt *.pt *.pth"), ("All files", "*.*")),
        )
        if selected:
            variable.set(selected)
            self._update_summaries()
