"""Card-prompt YAML editor UI."""

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import yaml

import generation
from services.config_store import _cards_yaml_text, _patch_yaml_text


class CardCreationMixin:
    def _build_card_creation_page(self, page):
        ttk.Label(
            page,
            text=(
                "Use the form editor for common fields, or switch to YAML for "
                "advanced editing."
            ),
            wraplength=760,
        ).pack(anchor="w", pady=(0, 8))
        self.card_prompt_pages = ttk.Notebook(page)
        self.card_prompt_pages.pack(fill="both", expand=True)
        self.card_prompt_editors = {}
        self.card_prompt_forms = {}
        paths = sorted(
            (*generation.CARD_DIR.rglob("*.yaml"), *generation.CARD_DIR.rglob("*.yml"))
        )
        for path in paths:
            self._add_card_prompt_editor(path)

    def _add_card_prompt_editor(self, path):
        page = ttk.Frame(self.card_prompt_pages, padding=8)
        self.card_prompt_pages.add(
            page, text=path.relative_to(generation.CARD_DIR).as_posix()
        )
        editor_pages = ttk.Notebook(page)
        editor_pages.pack(fill="both", expand=True)

        library_kind = next(
            (
                kind
                for kind, filename in generation.LIBRARY_FILES.items()
                if path.name == filename
            ),
            None,
        )
        if path.name == "cards.yaml":
            form_page = ttk.Frame(editor_pages, padding=8)
            editor_pages.add(form_page, text="Form")
            self._build_cards_form(path, form_page)
        elif library_kind:
            form_page = ttk.Frame(editor_pages, padding=8)
            editor_pages.add(form_page, text="Form")
            self._build_library_form(path, library_kind, form_page)

        yaml_page = ttk.Frame(editor_pages, padding=8)
        editor_pages.add(yaml_page, text="YAML")
        self._build_yaml_editor(path, yaml_page)

    def _build_yaml_editor(self, path, page):
        editor_frame = ttk.Frame(page)
        editor_frame.pack(fill="both", expand=True)
        editor = tk.Text(editor_frame, wrap="none", undo=True)
        editor.pack(side="left", fill="both", expand=True)
        vertical = ttk.Scrollbar(editor_frame, command=editor.yview)
        vertical.pack(side="right", fill="y")
        horizontal = ttk.Scrollbar(page, orient="horizontal", command=editor.xview)
        horizontal.pack(fill="x")
        editor.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        controls = ttk.Frame(page)
        controls.pack(fill="x", pady=(8, 0))
        status = tk.StringVar(value=str(path))
        ttk.Label(controls, textvariable=status).pack(side="left", fill="x", expand=True)
        ttk.Button(
            controls,
            text="Reload",
            command=lambda p=path, e=editor, s=status: self._load_card_prompt_file(
                p, e, s
            ),
        ).pack(side="right")
        ttk.Button(
            controls,
            text="Save",
            command=lambda p=path, e=editor, s=status: self._save_card_prompt_file(
                p, e, s
            ),
        ).pack(side="right", padx=(0, 8))
        self.card_prompt_editors[path] = (editor, status)
        self._load_card_prompt_file(path, editor, status)

    def _build_library_form(self, path, kind, page):
        state = {
            "path": path,
            "kind": kind,
            "data": {},
            "selected": None,
            "key": tk.StringVar(),
            "selector": tk.StringVar(),
            "prompt": None,
            "prompt_neg": None,
            "display": tk.StringVar(),
            "lora": None,
        }
        self._form_label(page, "Entry")
        row = ttk.Frame(page)
        row.pack(fill="x", pady=(0, 8))
        state["entry_selector"] = ttk.Combobox(
            row, textvariable=state["selector"], state="readonly"
        )
        state["entry_selector"].pack(side="left", fill="x", expand=True)
        state["entry_selector"].bind(
            "<<ComboboxSelected>>",
            lambda _event, s=state: self._select_library_entry(s),
        )
        ttk.Button(
            row, text="New entry", command=lambda s=state: self._new_library_entry(s)
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            row,
            text="Delete entry",
            command=lambda s=state: self._delete_library_entry(s),
        ).pack(side="left", padx=(8, 0))

        self._form_label(page, "Key")
        ttk.Entry(page, textvariable=state["key"]).pack(fill="x", pady=(0, 8))
        self._form_label(page, "Positive prompt")
        state["prompt"] = self._text_field(page, height=4)
        self._form_label(page, "Negative prompt (optional)")
        state["prompt_neg"] = self._text_field(page, height=3)
        self._form_label(page, "Default display (optional)")
        ttk.Entry(page, textvariable=state["display"]).pack(fill="x", pady=(0, 8))
        self._form_label(page, "LoRA references (optional YAML list or mapping)")
        state["lora"] = self._text_field(page, height=3)
        ttk.Button(
            page,
            text="Save entry",
            command=lambda s=state: self._save_library_entry(s),
        ).pack(anchor="e", pady=(8, 0))
        self.card_prompt_forms[path] = ("library", state)
        self._load_library_form(state)

    def _build_cards_form(self, path, page):
        state = {
            "path": path,
            "data": {},
            "set": tk.StringVar(),
            "display": tk.StringVar(),
            "defaults": {},
            "cards": {},
        }
        self._form_label(page, "Card set")
        row = ttk.Frame(page)
        row.pack(fill="x", pady=(0, 8))
        state["set_selector"] = ttk.Combobox(
            row, textvariable=state["set"], state="readonly"
        )
        state["set_selector"].pack(side="left", fill="x", expand=True)
        state["set_selector"].bind(
            "<<ComboboxSelected>>", lambda _event, s=state: self._select_card_set(s)
        )
        ttk.Button(
            row, text="New set", command=lambda s=state: self._new_card_set(s)
        ).pack(side="left", padx=(8, 0))

        self._form_label(page, "Set display name (optional)")
        ttk.Entry(page, textvariable=state["display"]).pack(fill="x", pady=(0, 8))
        ttk.Separator(page).pack(fill="x", pady=8)
        ttk.Label(
            page, text="Set global defaults", font=("TkDefaultFont", 11, "bold")
        ).pack(
            anchor="w", pady=(0, 4)
        )
        for kind in generation.LIBRARY_KINDS:
            if kind == "place":
                continue
            self._form_label(page, kind.replace("_", " ").title())
            variable = tk.StringVar()
            selector = ttk.Combobox(page, textvariable=variable, state="readonly")
            selector.pack(fill="x", pady=(0, 8))
            state["defaults"][kind] = (variable, selector)

        self._form_label(page, "LoRA preset")
        preset_variable = tk.StringVar()
        preset_selector = ttk.Combobox(
            page, textvariable=preset_variable, state="readonly"
        )
        preset_selector.pack(fill="x", pady=(0, 8))
        state["defaults"]["lora_preset"] = (preset_variable, preset_selector)
        self._form_label(page, "Custom positive prompt")
        state["defaults"]["prompt_pos"] = self._text_field(page, height=3)
        self._form_label(page, "Custom negative prompt")
        state["defaults"]["prompt_neg"] = self._text_field(page, height=3)

        ttk.Separator(page).pack(fill="x", pady=8)
        ttk.Label(page, text="Cards 1–18", font=("TkDefaultFont", 11, "bold")).pack(
            anchor="w", pady=(0, 4)
        )
        grid = ttk.Frame(page)
        grid.pack(fill="both", expand=True)
        for column in range(3):
            grid.columnconfigure(column, weight=1, uniform="card_column")
        for index in range(1, 19):
            card_name = f"card_{index:02d}"
            card_frame = ttk.LabelFrame(grid, text=card_name, padding=6)
            card_frame.grid(
                row=(index - 1) // 3,
                column=(index - 1) % 3,
                sticky="nsew",
                padx=4,
                pady=4,
            )
            card_state = {"fields": {}}
            for kind in generation.LIBRARY_KINDS:
                ttk.Label(
                    card_frame, text=kind.replace("_", " ").title()
                ).pack(anchor="w")
                variable = tk.StringVar()
                selector = ttk.Combobox(
                    card_frame, textvariable=variable, state="readonly"
                )
                selector.pack(fill="x", pady=2)
                card_state["fields"][kind] = (variable, selector)
            ttk.Label(card_frame, text="LoRA preset").pack(anchor="w")
            preset_variable = tk.StringVar()
            preset_selector = ttk.Combobox(
                card_frame, textvariable=preset_variable, state="readonly"
            )
            preset_selector.pack(fill="x", pady=2)
            card_state["fields"]["lora_preset"] = (
                preset_variable,
                preset_selector,
            )
            ttk.Label(card_frame, text="Positive prompt").pack(anchor="w")
            positive = self._text_field(card_frame, height=2)
            positive.pack_configure(pady=2)
            ttk.Label(card_frame, text="Negative prompt").pack(anchor="w")
            negative = self._text_field(card_frame, height=2)
            negative.pack_configure(pady=2)
            card_state["fields"]["prompt_pos"] = positive
            card_state["fields"]["prompt_neg"] = negative
            state["cards"][card_name] = card_state

        ttk.Button(
            page,
            text="Save set",
            command=lambda s=state: self._save_card_form(s),
        ).pack(anchor="e", pady=(8, 0))
        self.card_prompt_forms[path] = ("cards", state)
        self._load_cards_form(state)

    @staticmethod
    def _form_label(parent, text):
        ttk.Label(parent, text=text).pack(anchor="w", pady=(4, 2))

    @staticmethod
    def _text_field(parent, height):
        field = tk.Text(parent, height=height, wrap="word", undo=True)
        field.pack(fill="x", pady=(0, 8))
        return field

    @staticmethod
    def _field_text(field):
        return field.get("1.0", "end-1c").strip()

    @staticmethod
    def _set_field_text(field, value):
        field.delete("1.0", "end")
        if value is not None:
            field.insert("1.0", str(value))

    def _load_card_prompt_file(self, path, editor, status):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            messagebox.showerror("Could not load prompt file", str(error))
            return
        editor.delete("1.0", "end")
        editor.insert("1.0", text)
        status.set(str(path))

    def _save_card_prompt_file(self, path, editor, status):
        text = editor.get("1.0", "end-1c")
        try:
            parsed = yaml.load(text, Loader=generation.DuplicateKeyLoader)
        except (generation.ConfigError, yaml.YAMLError) as error:
            messagebox.showerror("Invalid YAML", str(error))
            return
        if parsed is not None and not isinstance(parsed, dict):
            messagebox.showerror(
                "Invalid YAML",
                f"{path.name} must contain a mapping at the top level.",
            )
            return
        try:
            original_text = path.read_text(encoding="utf-8")
            data = parsed if parsed is not None else {}
            saved_text = (
                _cards_yaml_text(original_text, data)
                if path.name == "cards.yaml"
                else _patch_yaml_text(original_text, data)
            )
        except OSError as error:
            messagebox.showerror("Could not load prompt file", str(error))
            return
        except yaml.YAMLError as error:
            messagebox.showerror("Invalid YAML", str(error))
            return
        self._write_card_prompt_text(path, saved_text, editor, status)

    def _write_card_prompt_text(self, path, text, editor=None, status=None):
        destination = path.resolve()
        try:
            destination.write_text(text, encoding="utf-8")
            written_text = destination.read_text(encoding="utf-8")
            if written_text != text:
                raise OSError(
                    f"Saved contents did not match the editor contents in {destination}."
                )
        except OSError as error:
            messagebox.showerror("Could not save prompt file", str(error))
            return False
        editor_data = self.card_prompt_editors.get(path)
        if editor is None and editor_data:
            editor, status = editor_data
        if editor is not None:
            editor.delete("1.0", "end")
            editor.insert("1.0", text)
        if status is not None:
            status.set(f"Saved {destination}")
        if path.name == "cards.yaml":
            self._load_sets()
        self._reload_card_prompt_form(path)
        messagebox.showinfo("Prompt file saved", f"Saved {path.name} to:\n{destination}")
        return True

    def _reload_card_prompt_form(self, path):
        form = self.card_prompt_forms.get(path)
        if form is None:
            return
        form_kind, state = form
        if form_kind == "cards":
            self._load_cards_form(state)
        else:
            self._load_library_form(state)

    def _save_form_data(self, state, data):
        path = state["path"]
        try:
            original_text = path.read_text(encoding="utf-8")
            saved_text = (
                _cards_yaml_text(original_text, data)
                if path.name == "cards.yaml"
                else _patch_yaml_text(original_text, data)
            )
        except (OSError, yaml.YAMLError) as error:
            messagebox.showerror("Could not save prompt file", str(error))
            return False
        return self._write_card_prompt_text(path, saved_text)

    def _load_library_form(self, state):
        try:
            state["data"] = generation.load_yaml(state["path"])
        except (generation.ConfigError, OSError) as error:
            messagebox.showerror("Could not load prompt file", str(error))
            return
        names = sorted(state["data"])
        state["entry_selector"].configure(values=names)
        if names:
            state["selector"].set(names[0])
            self._select_library_entry(state)
        else:
            self._new_library_entry(state)

    def _select_library_entry(self, state):
        name = state["selector"].get()
        entry = state["data"].get(name)
        if not isinstance(entry, dict):
            messagebox.showerror(
                "Invalid prompt entry", f"Entry '{name}' must be a YAML mapping."
            )
            return
        state["selected"] = name
        state["key"].set(name)
        self._set_field_text(state["prompt"], entry.get("prompt"))
        self._set_field_text(state["prompt_neg"], entry.get("prompt_neg"))
        state["display"].set(str(entry.get("default_display", "")))
        lora = entry.get("lora")
        self._set_field_text(
            state["lora"],
            yaml.safe_dump(lora, sort_keys=False, allow_unicode=True).rstrip()
            if lora is not None
            else "",
        )

    def _new_library_entry(self, state):
        state["selected"] = None
        state["selector"].set("")
        state["key"].set("")
        state["display"].set("")
        for field in (state["prompt"], state["prompt_neg"], state["lora"]):
            self._set_field_text(field, "")

    def _delete_library_entry(self, state):
        name = state["selected"]
        if not name:
            return
        if not messagebox.askyesno("Delete entry", f"Delete '{name}'?"):
            return
        data = dict(state["data"])
        data.pop(name, None)
        if self._save_form_data(state, data):
            self._load_library_form(state)

    def _save_library_entry(self, state):
        key = state["key"].get().strip()
        if not key:
            messagebox.showerror("Invalid entry", "Enter a key for this entry.")
            return
        original = state["selected"]
        if key != original and key in state["data"]:
            messagebox.showerror("Invalid entry", f"Entry '{key}' already exists.")
            return
        try:
            lora_text = self._field_text(state["lora"])
            lora = (
                yaml.load(lora_text, Loader=generation.DuplicateKeyLoader)
                if lora_text
                else None
            )
        except (generation.ConfigError, yaml.YAMLError) as error:
            messagebox.showerror("Invalid LoRA references", str(error))
            return
        if lora is not None and not isinstance(lora, (str, list, dict)):
            messagebox.showerror(
                "Invalid LoRA references",
                "LoRA references must be a string, list, or mapping.",
            )
            return
        entry = state["data"].get(original, {}) if original else {}
        if not isinstance(entry, dict):
            messagebox.showerror(
                "Invalid prompt entry", f"Entry '{original}' must be a YAML mapping."
            )
            return
        entry = dict(entry)
        prompt = self._field_text(state["prompt"])
        if prompt:
            entry["prompt"] = prompt
        else:
            entry.pop("prompt", None)
        prompt_neg = self._field_text(state["prompt_neg"])
        if prompt_neg:
            entry["prompt_neg"] = prompt_neg
        else:
            entry.pop("prompt_neg", None)
        display = state["display"].get().strip()
        if display:
            entry["default_display"] = display
        else:
            entry.pop("default_display", None)
        if lora is None:
            entry.pop("lora", None)
        else:
            entry["lora"] = lora
        data = dict(state["data"])
        if original and original != key:
            data.pop(original, None)
        data[key] = entry
        if self._save_form_data(state, data):
            self._load_library_form(state)
            state["selector"].set(key)
            self._select_library_entry(state)

    def _load_cards_form(self, state):
        try:
            state["data"] = generation.load_yaml(state["path"])
            libraries = {
                kind: generation.load_yaml(
                    generation.CARD_DIR / generation.LIBRARY_FILES[kind]
                )
                for kind in generation.LIBRARY_KINDS
            }
            presets_path = generation.WORKFLOW_DIR / "loras_preset.yaml"
            presets = generation.load_yaml(presets_path) if presets_path.exists() else {}
        except (generation.ConfigError, OSError) as error:
            messagebox.showerror("Could not load card data", str(error))
            return

        for kind, field in state["defaults"].items():
            if isinstance(field, tuple):
                _variable, selector = field
                choices = sorted(libraries[kind]) if kind in libraries else sorted(presets)
                selector.configure(values=["", *choices])
        for card_state in state["cards"].values():
            for kind, field in card_state["fields"].items():
                if isinstance(field, tuple):
                    _variable, selector = field
                    choices = (
                        sorted(libraries[kind]) if kind in libraries else sorted(presets)
                    )
                    selector.configure(values=["", *choices])

        names = sorted(state["data"])
        state["set_selector"].configure(values=names)
        if names:
            selected = state["set"].get()
            state["set"].set(selected if selected in state["data"] else names[0])
            self._select_card_set(state)
        else:
            state["set"].set("")
            state["display"].set("")
            self._set_card_form_values(state, {}, {})

    def _select_card_set(self, state):
        set_name = state["set"].get()
        set_data = state["data"].get(set_name)
        if not isinstance(set_data, dict):
            messagebox.showerror(
                "Invalid card set", f"Set '{set_name}' must be a YAML mapping."
            )
            return
        state["display"].set(str(set_data.get("display_name", "")))
        defaults_key = "_defaults" if "_defaults" in set_data else "set_defaults"
        defaults = set_data.get(defaults_key, {})
        if not isinstance(defaults, dict):
            messagebox.showerror(
                "Invalid card set", f"Set '{set_name}' defaults must be a mapping."
            )
            return
        self._set_card_form_values(state, defaults, set_data)

    def _set_card_form_values(self, state, defaults, set_data):
        for key, field in state["defaults"].items():
            value = defaults.get(key)
            if isinstance(field, tuple):
                variable, selector = field
                self._select_form_reference(selector, variable, value)
            else:
                self._set_field_text(field, value)

        for card_name, card_state in state["cards"].items():
            card_data = set_data.get(card_name, {})
            if not isinstance(card_data, dict):
                card_data = {}
            for key, field in card_state["fields"].items():
                value = card_data.get(key)
                if value == defaults.get(key):
                    value = None
                if isinstance(field, tuple):
                    variable, selector = field
                    self._select_form_reference(selector, variable, value)
                else:
                    self._set_field_text(field, value)

    @staticmethod
    def _select_form_reference(selector, variable, value):
        choices = list(selector.cget("values"))
        selected = "" if value is None else str(value)
        if selected and selected not in choices:
            choices.append(selected)
            selector.configure(values=choices)
        variable.set(selected)

    def _new_card_set(self, state):
        name = simpledialog.askstring("New card set", "Set key:")
        if not name:
            return
        name = name.strip()
        if not name or name in state["data"]:
            messagebox.showerror("Invalid card set", f"Set key '{name}' is empty or exists.")
            return
        state["data"][name] = {"_defaults": {}}
        state["set_selector"].configure(values=sorted(state["data"]))
        state["set"].set(name)
        self._select_card_set(state)

    def _save_card_form(self, state):
        set_name = state["set"].get()
        if not set_name or set_name not in state["data"]:
            messagebox.showerror("Invalid card set", "Select or create a card set first.")
            return
        set_data = state["data"][set_name]
        if not isinstance(set_data, dict):
            messagebox.showerror("Invalid card set", f"Set '{set_name}' must be a mapping.")
            return
        set_data = {}
        display = state["display"].get().strip()
        if display:
            set_data["display_name"] = display

        defaults = {}
        for key, field in state["defaults"].items():
            if isinstance(field, tuple):
                value = field[0].get().strip()
            else:
                value = self._field_text(field)
            if value:
                defaults[key] = value

        set_data["_defaults"] = defaults
        for card_name, card_state in state["cards"].items():
            card_data = {}
            for key, field in card_state["fields"].items():
                if isinstance(field, tuple):
                    value = field[0].get().strip()
                else:
                    value = self._field_text(field)
                if value and value != defaults.get(key):
                    card_data[key] = value
            set_data[card_name] = card_data

        data = dict(state["data"])
        data[set_name] = set_data
        if self._save_form_data(state, data):
            state["data"] = data
            self._select_card_set(state)
