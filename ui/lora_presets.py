"""LoRA preset editor UI."""

import math
import tkinter as tk
from tkinter import messagebox, ttk

import yaml

import generation
from services.config_store import _write_sorted_yaml


class LoraPresetsMixin:
    def _build_lora_presets_page(self, page):
        ttk.Label(
            page,
            text="Create and edit reusable LoRA presets. Select LoRAs, set their model/CLIP weights, then save the preset.",
            wraplength=760,
        ).pack(anchor="w", pady=(0, 8))
        name_row = ttk.Frame(page)
        name_row.pack(fill="x", pady=(0, 8))
        ttk.Label(name_row, text="Preset name").pack(side="left")
        self.preset_name_selector = ttk.Combobox(
            name_row, textvariable=self.preset_name, state="normal"
        )
        self.preset_name_selector.pack(
            side="left", fill="x", expand=True, padx=(8, 8)
        )
        ttk.Button(name_row, text="Load", command=self._load_selected_preset).pack(
            side="left"
        )
        ttk.Button(name_row, text="Save preset", command=self._save_lora_preset).pack(
            side="left", padx=(8, 0)
        )

        content = ttk.Panedwindow(page, orient="horizontal")
        content.pack(fill="both", expand=True)
        available = ttk.LabelFrame(content, text="Available LoRAs", padding=6)
        members = ttk.LabelFrame(content, text="Preset members", padding=6)
        content.add(available, weight=1)
        content.add(members, weight=2)

        available_row = ttk.Frame(available)
        available_row.pack(fill="both", expand=True)
        self.preset_lora_list = tk.Listbox(
            available_row, selectmode="extended", exportselection=False
        )
        self.preset_lora_list.pack(side="left", fill="both", expand=True)
        available_scrollbar = ttk.Scrollbar(
            available_row, command=self.preset_lora_list.yview
        )
        available_scrollbar.pack(side="right", fill="y")
        self.preset_lora_list.configure(yscrollcommand=available_scrollbar.set)
        ttk.Button(
            available,
            text="Add selected",
            command=self._add_selected_preset_loras,
        ).pack(anchor="w", pady=(6, 0))

        columns = ("name", "weight", "clip")
        self.preset_members = ttk.Treeview(
            members, columns=columns, show="headings", selectmode="extended"
        )
        for column, title, width in (
            ("name", "LoRA", 260),
            ("weight", "Weight", 90),
            ("clip", "CLIP", 90),
        ):
            self.preset_members.heading(column, text=title)
            self.preset_members.column(column, width=width, stretch=column == "name")
        self.preset_members.tag_configure("installed", foreground="#18753b")
        self.preset_members.tag_configure("missing", foreground="#a12622")
        self.preset_members.tag_configure("unconfigured", foreground="#a12622")
        self.preset_members.pack(fill="both", expand=True)
        self.preset_members.bind(
            "<<TreeviewSelect>>", self._load_selected_preset_member
        )

        weight_row = ttk.Frame(members)
        weight_row.pack(fill="x", pady=(8, 4))
        ttk.Label(weight_row, text="Weight").pack(side="left")
        ttk.Entry(weight_row, textvariable=self.preset_weight, width=10).pack(
            side="left", padx=(4, 12)
        )
        ttk.Label(weight_row, text="CLIP").pack(side="left")
        ttk.Entry(weight_row, textvariable=self.preset_clip, width=10).pack(
            side="left", padx=(4, 12)
        )
        ttk.Button(
            weight_row,
            text="Update selected",
            command=self._update_preset_member,
        ).pack(side="left")
        ttk.Button(
            weight_row,
            text="Remove selected",
            command=self._remove_preset_members,
        ).pack(side="left", padx=(8, 0))

    def _refresh_preset_editor(self):
        if not hasattr(self, "preset_lora_list"):
            return
        self.preset_lora_list.delete(0, "end")
        self.preset_lora_names = list(self.asset_entries["loras"])
        for index, name in enumerate(self.preset_lora_names):
            item = self.asset_entries["loras"][name]
            self.preset_lora_list.insert(
                "end", item.get("display_name", name)
            )
            self.preset_lora_list.itemconfigure(
                index, foreground=self._asset_color(item)
            )
        self.preset_members.delete(*self.preset_members.get_children())

    def _load_selected_preset(self):
        name = self.preset_name.get().strip()
        selection = self.preset_list.curselection()
        if not name and selection:
            name = self.preset_list.get(selection[0])
            self.preset_name.set(name)
        if not name:
            messagebox.showerror("Select a preset", "Select a preset or enter its name.")
            return
        try:
            presets = generation.load_yaml(
                generation.WORKFLOW_DIR / "loras_preset.yaml"
            )
        except (generation.ConfigError, OSError) as error:
            messagebox.showerror("Could not load presets", str(error))
            return
        refs = presets.get(name)
        if refs is None:
            messagebox.showerror(
                "Preset not found",
                f"No preset named '{name}' exists in workflow/loras_preset.yaml.",
            )
            return
        if not isinstance(refs, list):
            messagebox.showerror(
                "Invalid preset", f"Preset '{name}' must contain a list of LoRAs."
            )
            return
        self.preset_members.delete(*self.preset_members.get_children())
        try:
            for lora_name, weight, clip in generation.normalize_lora_refs(
                refs, f"preset '{name}'"
            ):
                weight = 0.7 if weight is None else float(weight)
                clip = weight if clip is None else float(clip)
                self.preset_members.insert(
                    "",
                    "end",
                    iid=str(lora_name),
                    values=(
                        self.asset_entries["loras"].get(str(lora_name), {}).get(
                            "display_name", str(lora_name)
                        ),
                        weight,
                        clip,
                    ),
                    tags=(
                        self._asset_tag(
                            self.asset_entries["loras"].get(str(lora_name))
                        ),
                    ),
                )
        except (generation.ConfigError, TypeError, ValueError) as error:
            messagebox.showerror("Invalid preset", str(error))

    def _preset_strengths(self):
        try:
            weight = float(self.preset_weight.get())
            clip = float(self.preset_clip.get())
        except ValueError:
            messagebox.showerror("Invalid strength", "Weight and CLIP must be numbers.")
            return None
        if not math.isfinite(weight) or not math.isfinite(clip):
            messagebox.showerror("Invalid strength", "Weight and CLIP must be finite numbers.")
            return None
        return weight, clip

    def _add_selected_preset_loras(self):
        selected = self.preset_lora_list.curselection()
        if not selected:
            messagebox.showerror("Select LoRAs", "Select one or more LoRAs to add.")
            return
        strengths = self._preset_strengths()
        if strengths is None:
            return
        weight, clip = strengths
        added = []
        for index in selected:
            name = self.preset_lora_names[index]
            display_name = self.asset_entries["loras"][name].get(
                "display_name", name
            )
            values = (display_name, weight, clip)
            if self.preset_members.exists(name):
                self.preset_members.item(
                    name,
                    values=values,
                    tags=(self._asset_tag(self.asset_entries["loras"].get(name)),),
                )
            else:
                self.preset_members.insert(
                    "",
                    "end",
                    iid=name,
                    values=values,
                    tags=(self._asset_tag(self.asset_entries["loras"].get(name)),),
                )
            added.append(name)
        self.preset_members.selection_set(added)

    def _load_selected_preset_member(self, _event=None):
        selection = self.preset_members.selection()
        if not selection:
            return
        _, weight, clip = self.preset_members.item(selection[0], "values")
        self.preset_weight.set(str(weight))
        self.preset_clip.set(str(clip))

    def _update_preset_member(self):
        selection = self.preset_members.selection()
        if not selection:
            messagebox.showerror(
                "Select preset members", "Select one or more preset members to update."
            )
            return
        strengths = self._preset_strengths()
        if strengths is None:
            return
        weight, clip = strengths
        for name in selection:
            display_name = self.asset_entries["loras"].get(name, {}).get(
                "display_name", name
            )
            self.preset_members.item(
                name,
                values=(display_name, weight, clip),
                tags=(self._asset_tag(self.asset_entries["loras"].get(name)),),
            )

    def _remove_preset_members(self):
        selection = self.preset_members.selection()
        if not selection:
            messagebox.showerror(
                "Select preset members", "Select one or more preset members to remove."
            )
            return
        self.preset_members.delete(*selection)

    def _save_lora_preset(self):
        name = self.preset_name.get().strip()
        if not name:
            messagebox.showerror("Preset name required", "Enter a name for this preset.")
            return
        members = []
        for item_id in self.preset_members.get_children():
            _, weight, clip = self.preset_members.item(item_id, "values")
            lora_name = item_id
            if lora_name not in self.asset_entries["loras"]:
                messagebox.showerror(
                    "Unknown LoRA", f"'{lora_name}' is not present in workflow/loras.yaml."
                )
                return
            members.append(
                {"name": lora_name, "weight": float(weight), "clip": float(clip)}
            )
        if not members:
            messagebox.showerror(
                "Empty preset", "Add at least one LoRA before saving a preset."
            )
            return
        path = generation.WORKFLOW_DIR / "loras_preset.yaml"
        try:
            presets = generation.load_yaml(path) if path.exists() else {}
            presets[name] = members
            _write_sorted_yaml(path, presets)
        except (generation.ConfigError, OSError, yaml.YAMLError, ValueError) as error:
            messagebox.showerror("Could not save preset", str(error))
            return
        selected_before_save = {
            self.preset_list.get(index) for index in self.preset_list.curselection()
        }
        self._load_image_choices(preserve_selected=selected_before_save)
        self._load_selected_preset()
        self._update_selected_preset_count()
        messagebox.showinfo("Preset saved", f"Saved '{name}' to {path.name}.")
