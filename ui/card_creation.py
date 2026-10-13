"""Card-prompt YAML editor UI."""

import tkinter as tk
from tkinter import messagebox, ttk

import yaml

import generation
from services.config_store import (
    _restore_top_level_inline_comments,
    _sorted_yaml_data,
    _top_level_inline_comments,
)


class CardCreationMixin:
    def _build_card_creation_page(self, page):
        ttk.Label(
            page,
            text="Edit the YAML prompt and card data files used for card creation.",
            wraplength=760,
        ).pack(anchor="w", pady=(0, 8))
        self.card_prompt_pages = ttk.Notebook(page)
        self.card_prompt_pages.pack(fill="both", expand=True)
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
            comments = _top_level_inline_comments(text)
            saved_text = (
                yaml.safe_dump(
                    _sorted_yaml_data(parsed),
                    sort_keys=False,
                    allow_unicode=True,
                )
                if parsed is not None
                else text
            )
            saved_text = _restore_top_level_inline_comments(saved_text, comments)
        except yaml.YAMLError as error:
            messagebox.showerror("Invalid YAML", str(error))
            return
        destination = path.resolve()
        try:
            destination.write_text(saved_text, encoding="utf-8")
            written_text = destination.read_text(encoding="utf-8")
            if written_text != saved_text:
                raise OSError(
                    f"Saved contents did not match the editor contents in {destination}."
                )
        except OSError as error:
            messagebox.showerror("Could not save prompt file", str(error))
            return
        editor.delete("1.0", "end")
        editor.insert("1.0", saved_text)
        status.set(f"Saved {destination}")
        if path.name == "cards.yaml":
            self._load_sets()
        messagebox.showinfo(
            "Prompt file saved",
            f"Saved {path.name} to:\n{destination}",
        )
