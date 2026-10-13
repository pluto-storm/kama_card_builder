"""Depth and image generation controls and process launching."""

import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import generation
from ui.constants import PATHS_FILE, ROOT


class GenerationControlsMixin:
    def _build_depth_page(self, page):
        ttk.Label(
            page,
            text=(
                "Select one image or a folder of images to create depth maps. "
                "For folders, nested folders are preserved in the output."
            ),
            wraplength=760,
        ).pack(anchor="w", pady=(0, 12))
        self._add_comfyui_controls(page)
        ttk.Label(page, text="Image file or folder").pack(anchor="w")
        input_row = ttk.Frame(page)
        input_row.pack(fill="x", pady=(4, 12))
        ttk.Entry(input_row, textvariable=self.depth_input, state="readonly").pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(input_row, text="Select file...", command=self._browse_depth_file).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(input_row, text="Select folder...", command=self._browse_depth_folder).pack(
            side="left", padx=(8, 0)
        )

        ttk.Label(page, text="Depth output folder").pack(anchor="w")
        output_row = ttk.Frame(page)
        output_row.pack(fill="x", pady=(4, 0))
        ttk.Entry(output_row, textvariable=self.depth_output).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(
            output_row, text="Choose...", command=self._browse_depth_output
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            output_row, text="Open output folder", command=self._open_depth_output
        ).pack(side="left", padx=(8, 0))
        button = ttk.Button(
            page,
            text="Run depth generation",
            command=lambda: self._start_generation("depth_maps"),
        )
        button.pack(anchor="w", pady=(16, 0))
        self.action_buttons.append(button)

    def _build_image_page(self, page):
        ttk.Label(
            page,
            text="Generate images and their depth outputs using the selected generation config.",
            wraplength=760,
        ).pack(anchor="w", pady=(0, 12))
        self._add_comfyui_controls(page)
        ttk.Label(page, text="Generation config").pack(anchor="w")
        config_row = ttk.Frame(page)
        config_row.pack(fill="x", pady=(4, 8))
        ttk.Entry(config_row, textvariable=self.generate_file).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(config_row, text="Browse...", command=self._browse_generate_file).pack(
            side="left", padx=(8, 0)
        )
        ttk.Label(page, text="Checkpoint").pack(anchor="w")
        self.checkpoint_selector = ttk.Combobox(
            page, textvariable=self.checkpoint_selection, state="readonly"
        )
        self.checkpoint_selector.pack(fill="x", pady=(4, 8))
        self.checkpoint_selector.bind("<<ComboboxSelected>>", self._select_generation_checkpoint)
        ttk.Label(page, text="LoRA presets to apply to selected sets").pack(
            anchor="w", pady=(4, 0)
        )
        preset_frame = ttk.Frame(page)
        preset_frame.pack(fill="x", pady=(4, 4))
        self.preset_list = tk.Listbox(
            preset_frame, selectmode="extended", exportselection=False, height=4
        )
        self.preset_list.pack(side="left", fill="x", expand=True)
        preset_scrollbar = ttk.Scrollbar(
            preset_frame, command=self.preset_list.yview
        )
        preset_scrollbar.pack(side="right", fill="y")
        self.preset_list.configure(yscrollcommand=preset_scrollbar.set)
        self.preset_list.bind(
            "<<ListboxSelect>>", self._update_selected_preset_count
        )
        ttk.Label(page, textvariable=self.selected_preset_count).pack(anchor="e")
        ttk.Label(page, text="Card sets to generate").pack(anchor="w", pady=(8, 0))
        sets_frame = ttk.Frame(page)
        sets_frame.pack(fill="both", expand=True, pady=(4, 8))
        self.set_list = tk.Listbox(
            sets_frame, selectmode="extended", exportselection=False, height=12
        )
        self.set_list.pack(side="left", fill="both", expand=True)
        set_scrollbar = ttk.Scrollbar(sets_frame, command=self.set_list.yview)
        set_scrollbar.pack(side="right", fill="y")
        self.set_list.configure(yscrollcommand=set_scrollbar.set)
        self.set_list.bind("<<ListboxSelect>>", self._update_selected_count)
        set_controls = ttk.Frame(page)
        set_controls.pack(fill="x")
        ttk.Button(set_controls, text="Select all", command=self._select_all_sets).pack(
            side="left"
        )
        ttk.Button(set_controls, text="Clear", command=self._clear_sets).pack(
            side="left", padx=(8, 0)
        )
        ttk.Label(set_controls, textvariable=self.selected_count).pack(
            side="right", padx=(8, 0)
        )
        self._path_summary(page, ("output_dir", "comfyui_url"))
        ttk.Button(
            page,
            text="Open image output folder",
            command=self._open_image_output,
        ).pack(anchor="w", pady=(8, 0))
        button = ttk.Button(
            page,
            text="Run image generation",
            command=lambda: self._start_generation("generate_images"),
        )
        button.pack(anchor="w", pady=(16, 0))
        self.action_buttons.append(button)

    def _browse_generate_file(self):
        selected = filedialog.askopenfilename(
            initialdir=str(ROOT),
            filetypes=(("YAML files", "*.yaml *.yml"), ("All files", "*.*")),
        )
        if selected:
            self.generate_file.set(selected)
            self._load_sets()

    def _load_image_choices(self, gen_config=None, preserve_selected=None):
        try:
            checkpoints = generation.load_yaml(
                generation.WORKFLOW_DIR / "checkpoints.yaml"
            )
            presets = generation.load_yaml(
                generation.WORKFLOW_DIR / "loras_preset.yaml"
            )
            if gen_config is None:
                gen_config = generation.load_yaml(
                    Path(self.generate_file.get()).expanduser()
                )
        except (generation.ConfigError, OSError) as error:
            messagebox.showerror("Could not load image options", str(error))
            return

        checkpoint_names = list(checkpoints)
        checkpoint = gen_config.get("checkpoint_to_use", "")
        if checkpoint not in checkpoints and checkpoint_names:
            checkpoint = checkpoint_names[0]
        self.checkpoint_selection.set(checkpoint)
        self.checkpoint_selector.configure(values=checkpoint_names)
        self._set_checkpoint_style(checkpoint)
        preset_names = list(presets)
        self.preset_set_names = preset_names
        self.preset_list.delete(0, "end")
        for name in preset_names:
            self.preset_list.insert("end", name)
        selected_presets = set(
            generation.as_list(gen_config.get("lora_presets", []))
        )
        if preserve_selected is not None:
            selected_presets = set(preserve_selected)
        for index, name in enumerate(preset_names):
            if name in selected_presets:
                self.preset_list.selection_set(index)
        self.preset_name_selector.configure(values=preset_names)
        self._update_selected_preset_count()
        self._refresh_preset_editor()

    def _select_generation_checkpoint(self, _event=None):
        checkpoint_name = self.checkpoint_selector.get()
        self.checkpoint_selection.set(checkpoint_name)
        self._set_checkpoint_style(checkpoint_name)

    def _load_sets(self):
        try:
            cards = generation.load_yaml(generation.CARD_DIR / "cards.yaml")
            gen_config = generation.load_yaml(Path(self.generate_file.get()).expanduser())
        except (generation.ConfigError, OSError) as error:
            self.set_list.delete(0, "end")
            self.selected_count.set("0 sets selected")
            messagebox.showerror("Could not load card sets", str(error))
            return

        selected_sets = set(generation.as_list(gen_config.get("sets_to_generate", [])))
        self.set_list.delete(0, "end")
        self.set_display_names = {}
        for index, (name, data) in enumerate(cards.items()):
            display_name = data.get("display_name") if isinstance(data, dict) else None
            label = f"{name} — {display_name}" if display_name else name
            self.set_display_names[name] = label
            self.set_list.insert("end", label)
            if name in selected_sets:
                self.set_list.selection_set(index)
        self._update_selected_count()
        self._load_image_choices(gen_config)

    def _browse_depth_file(self):
        selected = filedialog.askopenfilename(
            initialdir=str(ROOT),
            filetypes=(
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp"),
                ("All files", "*.*"),
            ),
        )
        if selected:
            self.depth_input.set(selected)

    def _browse_depth_folder(self):
        selected = filedialog.askdirectory(initialdir=str(ROOT))
        if selected:
            self.depth_input.set(selected)

    def _browse_depth_output(self):
        initial_dir = Path(self.depth_output.get()).expanduser()
        if not initial_dir.is_dir():
            initial_dir = ROOT
        selected = filedialog.askdirectory(initialdir=str(initial_dir))
        if selected:
            self.depth_output.set(selected)

    def _open_depth_output(self):
        output_dir = Path(self.depth_output.get()).expanduser()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(output_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(output_dir)])
            else:
                subprocess.Popen(["xdg-open", str(output_dir)])
        except OSError as error:
            messagebox.showerror("Could not open output folder", str(error))

    def _open_image_output(self):
        try:
            raw_paths = self._raw_ui_paths()
            output_value = raw_paths.get("output_dir")
            if not output_value:
                raise generation.ConfigError(
                    "Setup must define 'output_dir' before opening the image output folder."
                )
            expanded = generation.expand_vars(
                output_value, raw_paths, label="paths.local.yaml 'output_dir'"
            )
            output_dir = Path(expanded).expanduser()
            if not output_dir.is_absolute():
                output_dir = ROOT / output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(output_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(output_dir)])
            else:
                subprocess.Popen(["xdg-open", str(output_dir)])
        except (generation.ConfigError, OSError, ValueError) as error:
            messagebox.showerror("Could not open image output folder", str(error))

    def _select_all_sets(self):
        self.set_list.selection_set(0, "end")
        self._update_selected_count()

    def _clear_sets(self):
        self.set_list.selection_clear(0, "end")
        self._update_selected_count()

    def _update_selected_count(self, _event=None):
        count = len(self.set_list.curselection())
        self.selected_count.set(f"{count} set{'s' if count != 1 else ''} selected")

    def _update_selected_preset_count(self, _event=None):
        count = len(self.preset_list.curselection())
        self.selected_preset_count.set(
            f"{count} preset{'s' if count != 1 else ''} selected"
        )

    def _start_generation(self, mode):
        if not self._save_paths(show_confirmation=False):
            return
        config_path = Path(self.generate_file.get()).expanduser()
        try:
            generate_argument = str(config_path.resolve().relative_to(ROOT))
        except ValueError:
            generate_argument = str(config_path.resolve())
        command = [
            sys.executable,
            "-u",
            str(ROOT / "generation.py"),
            "--paths",
            str(PATHS_FILE),
            "--generate",
            generate_argument,
            "--mode",
            mode,
        ]
        if mode == "depth_maps":
            input_path = Path(self.depth_input.get()).expanduser()
            if not input_path.exists():
                messagebox.showerror(
                    "Select depth input",
                    "Select an existing image file or folder before starting depth generation.",
                )
                return
            output_path = Path(self.depth_output.get()).expanduser()
            if not output_path.is_absolute():
                output_path = (ROOT / output_path).resolve()
            command.extend(["--depth-input", str(input_path.resolve())])
            command.extend(["--depth-output", str(output_path)])
        else:
            selected_sets = [
                name
                for index, name in enumerate(self.set_display_names)
                if index in self.set_list.curselection()
            ]
            if not selected_sets:
                messagebox.showerror(
                    "Select card sets",
                    "Select at least one card set before starting image generation.",
                )
                return
            command.append("--sets")
            command.extend(selected_sets)
            checkpoint = self.checkpoint_selection.get().strip()
            if not checkpoint:
                messagebox.showerror(
                    "Select a checkpoint",
                    "Choose a checkpoint before starting image generation.",
                )
                return
            command.extend(["--checkpoint", checkpoint])
            selected_presets = [
                self.preset_list.get(index)
                for index in self.preset_list.curselection()
            ]
            command.append("--lora-presets")
            command.extend(selected_presets)
        self._append_output(f"> {mode.replace('_', ' ').title()}\n")
        self.status.set("Running...")
        for button in self.action_buttons:
            button.configure(state="disabled")
        threading.Thread(
            target=self._run_process,
            args=(command,),
            daemon=True,
        ).start()

    def _run_process(self, command):
        try:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in process.stdout:
                self.messages.put(("output", line))
            return_code = process.wait()
            self.messages.put(("finished", return_code))
        except OSError as error:
            self.messages.put(("error", str(error)))
