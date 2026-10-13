"""Local model catalog and registration UI."""

import os
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse
import webbrowser

import yaml

import generation
from services.config_store import _model_metadata_template, _write_sorted_yaml
from services.model_catalog import asset_display_name, asset_file_path, asset_tag
from ui.constants import ROOT


class ModelCatalogMixin:
    def _build_asset_page(self, page, kind):
        title = "LoRA" if kind == "loras" else "Checkpoint"
        ttk.Label(
            page,
            text=(
                f"Installed status is based on whether each catalog file exists in its configured "
                f"{'LoRA' if kind == 'loras' else 'checkpoint'} folder."
            ),
            wraplength=760,
        ).pack(anchor="w", pady=(0, 10))
        actions = ttk.Frame(page)
        actions.pack(fill="x", pady=(0, 6))
        get_button = ttk.Button(
            actions,
            text="Get it here",
            command=lambda: self._open_asset_source(kind),
            state="disabled",
        )
        get_button.pack(side="left")
        put_button = ttk.Button(
            actions,
            text="Put it here",
            command=lambda: self._open_asset_folder(kind),
            state="disabled",
        )
        put_button.pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="Refresh status",
            command=lambda: self._load_asset_catalog(kind),
        ).pack(side="right")
        self.asset_get_buttons[kind] = get_button
        self.asset_put_buttons[kind] = put_button

        body = ttk.Panedwindow(page, orient="vertical")
        body.pack(fill="both", expand=True)
        list_frame = ttk.Frame(body)
        details_frame = ttk.LabelFrame(body, text=f"{title} details", padding=6)
        body.add(list_frame, weight=3)
        body.add(details_frame, weight=2)

        columns = ("status", "file")
        tree = ttk.Treeview(list_frame, columns=columns, show="tree headings")
        tree.heading("#0", text=title)
        tree.heading("status", text="Status")
        tree.heading("file", text="File")
        tree.column("#0", width=250, stretch=True)
        tree.column("status", width=100, stretch=False)
        tree.column("file", width=440, stretch=True)
        vertical = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(list_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.tag_configure("installed", foreground="#18753b")
        tree.tag_configure("missing", foreground="#a12622")
        tree.tag_configure("unconfigured", foreground="#a12622")
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        tree.bind("<<TreeviewSelect>>", lambda _event, k=kind: self._select_asset(k))
        self.asset_trees[kind] = tree

        details = tk.Text(details_frame, height=8, wrap="word", state="disabled")
        detail_scroll = ttk.Scrollbar(details_frame, command=details.yview)
        details.configure(yscrollcommand=detail_scroll.set)
        details.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")
        self.asset_details[kind] = details

    def _build_add_model_page(self, page):
        ttk.Label(
            page,
            text=(
                "Register a checkpoint or LoRA that is already installed. "
                "Choose its model file and provide any additional catalog fields as YAML."
            ),
            wraplength=760,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))

        ttk.Label(page, text="Model type").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=5
        )
        model_type_selector = ttk.Combobox(
            page,
            textvariable=self.model_type,
            values=("checkpoint", "lora"),
            state="readonly",
            width=24,
        )
        model_type_selector.grid(row=1, column=1, sticky="w", pady=5)
        model_type_selector.bind(
            "<<ComboboxSelected>>", self._change_model_metadata_template
        )

        ttk.Label(page, text="Catalog key").grid(
            row=2, column=0, sticky="w", padx=(0, 8), pady=5
        )
        ttk.Entry(page, textvariable=self.model_key).grid(
            row=2, column=1, columnspan=2, sticky="ew", pady=5
        )

        ttk.Label(page, text="Installed model file").grid(
            row=3, column=0, sticky="w", padx=(0, 8), pady=5
        )
        file_row = ttk.Frame(page)
        file_row.grid(row=3, column=1, columnspan=2, sticky="ew", pady=5)
        ttk.Entry(file_row, textvariable=self.model_file, state="readonly").pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(
            file_row, text="Browse...", command=self._browse_model_file
        ).pack(side="left", padx=(8, 0))

        ttk.Label(page, text="Additional YAML fields").grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(12, 4)
        )
        ttk.Label(
            page,
            text=(
                "Enter a YAML mapping, for example source, base_model, prompt, "
                "trigger_words, or sampler_defaults. The selected file supplies the file field."
            ),
            wraplength=760,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(0, 6))
        metadata_frame = ttk.Frame(page)
        metadata_frame.grid(row=6, column=0, columnspan=3, sticky="nsew")
        self.model_metadata = tk.Text(metadata_frame, height=14, wrap="none", undo=True)
        self.model_metadata.pack(side="left", fill="both", expand=True)
        metadata_scroll = ttk.Scrollbar(
            metadata_frame, command=self.model_metadata.yview
        )
        metadata_scroll.pack(side="right", fill="y")
        self.model_metadata.configure(yscrollcommand=metadata_scroll.set)
        self.model_metadata_template = _model_metadata_template(self.model_type.get())
        self.model_metadata.insert("1.0", self.model_metadata_template)
        ttk.Button(
            page,
            text="Add to catalog",
            command=self._add_model_to_catalog,
        ).grid(row=7, column=0, sticky="w", pady=(10, 0))
        page.columnconfigure(1, weight=1)
        page.rowconfigure(6, weight=1)

    def _change_model_metadata_template(self, _event=None):
        current_text = self.model_metadata.get("1.0", "end-1c")
        if current_text != self.model_metadata_template:
            if not messagebox.askyesno(
                "Replace additional YAML fields?",
                "Changing model type will replace the current YAML editor contents. Continue?",
            ):
                self.model_type.set(
                    "lora" if self.model_type.get() == "checkpoint" else "checkpoint"
                )
                return
        self.model_metadata_template = _model_metadata_template(self.model_type.get())
        self.model_metadata.delete("1.0", "end")
        self.model_metadata.insert("1.0", self.model_metadata_template)

    def _browse_model_file(self):
        kind = self.model_type.get()
        path_key = "checkpoints_dir" if kind == "checkpoint" else "loras_dir"
        try:
            raw_paths = self._raw_ui_paths()
            initial_dir = Path(
                generation.expand_vars(
                    raw_paths.get(path_key, ""),
                    raw_paths,
                    label=f"paths.local.yaml '{path_key}'",
                )
            ).expanduser()
        except (generation.ConfigError, OSError, ValueError):
            initial_dir = ROOT
        if not initial_dir.is_dir():
            initial_dir = ROOT
        selected = filedialog.askopenfilename(
            initialdir=str(initial_dir),
            filetypes=(
                ("Model files", "*.safetensors *.ckpt *.pt *.pth"),
                ("All files", "*.*"),
            ),
        )
        if selected:
            self.model_file.set(selected)
            if not self.model_key.get().strip():
                self.model_key.set(Path(selected).stem)

    def _add_model_to_catalog(self):
        kind = self.model_type.get()
        if kind not in {"checkpoint", "lora"}:
            messagebox.showerror("Select model type", "Choose checkpoint or lora.")
            return
        name = self.model_key.get().strip()
        if not name:
            messagebox.showerror("Catalog key required", "Enter a catalog key.")
            return
        selected_file = Path(self.model_file.get()).expanduser()
        if not selected_file.is_file():
            messagebox.showerror(
                "Select an installed model",
                "Choose an existing checkpoint or LoRA model file.",
            )
            return

        path_key = "checkpoints_dir" if kind == "checkpoint" else "loras_dir"
        try:
            raw_paths = self._raw_ui_paths()
            root_value = raw_paths.get(path_key)
            if not root_value:
                raise generation.ConfigError(
                    f"Setup must define '{path_key}' before adding this model."
                )
            model_root = Path(
                generation.expand_vars(
                    root_value, raw_paths, label=f"paths.local.yaml '{path_key}'"
                )
            ).expanduser()
            if not model_root.is_absolute():
                model_root = ROOT / model_root
            model_root = model_root.resolve()
            selected_file = selected_file.resolve()
            try:
                relative_file = selected_file.relative_to(model_root)
            except ValueError as error:
                raise generation.ConfigError(
                    f"Select a model file located inside the configured '{path_key}' folder:\n"
                    f"{model_root}"
                ) from error
            metadata_text = self.model_metadata.get("1.0", "end-1c")
            metadata = yaml.load(
                metadata_text, Loader=generation.DuplicateKeyLoader
            )
            if metadata is None:
                metadata = {}
            if not isinstance(metadata, dict):
                raise generation.ConfigError(
                    "Additional YAML fields must be a mapping."
                )
            if "file" in metadata:
                raise generation.ConfigError(
                    "Do not include 'file' in Additional YAML fields; "
                    "the selected model file is used automatically."
                )
            catalog_path = generation.WORKFLOW_DIR / (
                "checkpoints.yaml" if kind == "checkpoint" else "loras.yaml"
            )
            catalog = generation.load_yaml(catalog_path)
            if name in catalog:
                raise generation.ConfigError(
                    f"{kind} '{name}' already exists in {catalog_path.name}."
                )
            entry = {
                "file": f"${{{path_key}}}/{relative_file.as_posix()}",
                **metadata,
            }
            catalog[name] = entry
            _write_sorted_yaml(catalog_path, catalog)
        except (generation.ConfigError, OSError, ValueError, yaml.YAMLError) as error:
            messagebox.showerror("Could not add model", str(error))
            return

        catalog_kind = "checkpoints" if kind == "checkpoint" else "loras"
        self._load_asset_catalog(catalog_kind, show_errors=False)
        self._load_image_choices()
        self.model_key.set("")
        self.model_file.set("")
        self.model_metadata_template = _model_metadata_template(kind)
        self.model_metadata.delete("1.0", "end")
        self.model_metadata.insert("1.0", self.model_metadata_template)
        messagebox.showinfo(
            "Model added",
            f"Added '{name}' to {catalog_path.name}.",
        )

    def _asset_file_path(self, kind, name, entry, raw_paths):
        return asset_file_path(kind, name, entry, raw_paths, ROOT)

    def _asset_display_name(self, kind, name, entry, raw_paths, file_path):
        return asset_display_name(kind, name, entry, raw_paths, file_path, ROOT)

    @staticmethod
    def _asset_tag(item):
        return asset_tag(item)

    def _asset_color(self, item):
        installed = "#45b86b" if self.dark_mode else "#18753b"
        missing = "#ff6b65" if self.dark_mode else "#a12622"
        return {
            "installed": installed,
            "missing": missing,
            "unconfigured": missing,
        }[self._asset_tag(item)]

    def _load_asset_catalog(self, kind, show_errors=True):
        tree = self.asset_trees[kind]
        tree.delete(*tree.get_children())
        self.asset_entries[kind].clear()
        catalog_file = (
            generation.WORKFLOW_DIR / "loras.yaml"
            if kind == "loras"
            else generation.WORKFLOW_DIR / "checkpoints.yaml"
        )
        try:
            catalog = generation.load_yaml(catalog_file)
            raw_paths = self._raw_ui_paths()
        except (generation.ConfigError, OSError) as error:
            tree.insert("", "end", iid="catalog-error", text="Catalog unavailable",
                        values=("Error", str(error)), tags=("unconfigured",))
            self._set_asset_details(kind, str(error))
            if show_errors:
                messagebox.showerror("Could not load catalog", str(error))
            return

        entries = {
            name: entry
            for name, entry in catalog.items()
            if name != "lora_presets" and isinstance(entry, dict)
        }
        for name, entry in entries.items():
            path_error = None
            try:
                file_path = self._asset_file_path(kind, name, entry, raw_paths)
                status = "Installed" if file_path.is_file() else "Missing"
                tag = "installed" if status == "Installed" else "missing"
            except (generation.ConfigError, OSError, TypeError, ValueError) as error:
                file_path = None
                path_error = str(error)
                status = "Unconfigured"
                tag = "unconfigured"
            self.asset_entries[kind][name] = {
                "entry": entry,
                "path": file_path,
                "error": path_error,
                "display_name": self._asset_display_name(
                    kind, name, entry, raw_paths, file_path
                ),
            }
            tree.insert(
                "",
                "end",
                iid=name,
                text=self.asset_entries[kind][name]["display_name"],
                values=(status, str(file_path) if file_path else "Path unavailable"),
                tags=(tag,),
            )
        self._select_asset(kind)
        if kind == "loras":
            self._refresh_preset_editor()
        elif hasattr(self, "checkpoint_selector"):
            self._refresh_checkpoint_statuses()

    def _refresh_checkpoint_statuses(self):
        checkpoint_names = list(self.asset_entries["checkpoints"])
        self.checkpoint_selector.configure(values=checkpoint_names)
        selected_checkpoint = self.checkpoint_selection.get()
        self._set_checkpoint_style(selected_checkpoint)

    def _set_checkpoint_style(self, checkpoint_name):
        item = self.asset_entries["checkpoints"].get(checkpoint_name)
        style = (
            "CheckpointInstalled.TCombobox"
            if self._asset_tag(item) == "installed"
            else "CheckpointMissing.TCombobox"
        )
        self.checkpoint_selector.configure(style=style)

    def _set_asset_details(self, kind, text):
        details = self.asset_details[kind]
        details.configure(state="normal")
        details.delete("1.0", "end")
        details.insert("1.0", text)
        details.configure(state="disabled")

    def _select_asset(self, kind):
        tree = self.asset_trees[kind]
        selection = tree.selection()
        if not selection or selection[0] not in self.asset_entries[kind]:
            self.asset_get_buttons[kind].configure(state="disabled")
            self.asset_put_buttons[kind].configure(state="disabled")
            return
        name = selection[0]
        item = self.asset_entries[kind][name]
        details = yaml.safe_dump(item["entry"], sort_keys=False)
        if item["path"] is not None:
            details += f"\nInstalled file:\n{item['path']}\n"
        if item["error"]:
            details += f"\nPath issue:\n{item['error']}\n"
        self._set_asset_details(kind, details)
        self.asset_put_buttons[kind].configure(
            state="normal" if item["path"] is not None else "disabled"
        )
        source = item["entry"].get("source")
        parsed = urlparse(source) if isinstance(source, str) else None
        self.asset_get_buttons[kind].configure(
            state="normal"
            if parsed and parsed.scheme in {"http", "https"} and parsed.netloc
            else "disabled"
        )

    def _selected_asset(self, kind):
        selection = self.asset_trees[kind].selection()
        if not selection:
            title = "LoRA" if kind == "loras" else "Checkpoint"
            messagebox.showerror(f"Select a {title}", f"Select a {title.lower()} from the list.")
            return None
        return self.asset_entries[kind].get(selection[0])

    def _open_asset_source(self, kind):
        item = self._selected_asset(kind)
        if item is None:
            return
        source = item["entry"].get("source")
        parsed = urlparse(source) if isinstance(source, str) else None
        if not parsed or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            messagebox.showerror("Invalid source URL", "This catalog entry has no valid HTTP source URL.")
            return
        if not webbrowser.open(source):
            messagebox.showerror("Could not open source", f"Could not open {source}")

    def _open_asset_folder(self, kind):
        item = self._selected_asset(kind)
        if item is None:
            return
        path = item["path"]
        if path is None:
            messagebox.showerror(
                "Install folder unavailable",
                item["error"] or "The install folder could not be resolved from Setup paths.",
            )
            return
        folder = path.parent
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as error:
            messagebox.showerror("Could not open install folder", str(error))
