"""Theme and widget color behavior."""

import tkinter as tk
from tkinter import ttk


class ThemeMixin:
    def _configure_dark_mode(self, style):
        if self.dark_mode:
            background = "#202124"
            surface = "#292a2d"
            field = "#17181a"
            foreground = "#e8eaed"
            muted = "#bdc1c6"
            accent = "#3c7dd9"
            border = "#4b4d50"
            selected_tab = "#383a3e"
            active_tab = "#323438"
            scrollbar_trough = background
        else:
            background = "#f3f4f6"
            surface = "#e2e5e9"
            field = "#ffffff"
            foreground = "#202124"
            muted = "#5f6368"
            accent = "#2f6fca"
            border = "#b8bdc4"
            selected_tab = "#ffffff"
            active_tab = "#eceff2"
            scrollbar_trough = "#e8eaed"
        style.theme_use("clam")
        self.root.configure(background=background)
        style.configure(
            "Comfy.Online.TLabel",
            background=background,
            foreground="#45b86b" if self.dark_mode else "#18753b",
        )
        style.configure(
            "Comfy.Offline.TLabel",
            background=background,
            foreground="#ff6b65" if self.dark_mode else "#a12622",
        )
        style.configure(
            "Comfy.Unknown.TLabel",
            background=background,
            foreground="#f0bd4f" if self.dark_mode else "#8a5b00",
        )
        style.configure(".", background=background, foreground=foreground)
        style.configure("TFrame", background=background)
        style.configure("TLabel", background=background, foreground=foreground)
        style.configure(
            "TButton",
            background=surface,
            foreground=foreground,
            bordercolor=border,
            focuscolor=accent,
            padding=6,
        )
        style.map(
            "TButton",
            background=[("active", "#3b3d40"), ("disabled", background)],
            foreground=[("disabled", muted)],
        )
        style.configure(
            "TEntry",
            fieldbackground=field,
            foreground=foreground,
            insertcolor=foreground,
            bordercolor=border,
        )
        style.configure(
            "TCombobox",
            fieldbackground=field,
            foreground=foreground,
            background=surface,
            arrowcolor=foreground,
            bordercolor="#4b4d50",
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", field)],
            foreground=[("readonly", foreground)],
            selectbackground=[("readonly", accent)],
            selectforeground=[("readonly", foreground)],
        )
        for status, color in (
            (
                "Installed",
                "#45b86b" if self.dark_mode else "#18753b",
            ),
            (
                "Missing",
                "#ff6b65" if self.dark_mode else "#a12622",
            ),
        ):
            checkpoint_style = f"Checkpoint{status}.TCombobox"
            style.configure(
                checkpoint_style,
                fieldbackground=field,
                foreground=color,
                background=surface,
                arrowcolor=foreground,
                bordercolor=border,
            )
            style.map(
                checkpoint_style,
                fieldbackground=[("readonly", field)],
                foreground=[("readonly", color)],
                selectbackground=[("readonly", accent)],
                selectforeground=[("readonly", foreground)],
            )
        style.configure(
            "TNotebook",
            background=background,
            bordercolor=background,
            tabmargins=(2, 4, 2, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=surface,
            foreground=muted,
            padding=(10, 6),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", selected_tab), ("active", active_tab)],
            foreground=[("selected", foreground), ("active", foreground)],
        )
        style.configure(
            "TLabelframe",
            background=background,
            foreground=foreground,
            bordercolor=border,
        )
        style.configure("TLabelframe.Label", background=background, foreground=foreground)
        style.configure(
            "Treeview",
            background=field,
            fieldbackground=field,
            foreground=foreground,
            bordercolor=border,
            rowheight=24,
        )
        style.map(
            "Treeview",
            background=[("selected", accent)],
            foreground=[("selected", foreground)],
        )
        style.configure(
            "Treeview.Heading",
            background=surface,
            foreground=foreground,
            relief="flat",
        )
        style.configure(
            "TScrollbar",
            background=surface,
            troughcolor=scrollbar_trough,
            arrowcolor=foreground,
            bordercolor=background,
        )
        self.root.option_add("*Text.background", field)
        self.root.option_add("*Text.foreground", foreground)
        self.root.option_add("*Text.insertBackground", foreground)
        self.root.option_add("*Text.selectBackground", accent)
        self.root.option_add("*Text.selectForeground", foreground)
        self.root.option_add("*Listbox.background", field)
        self.root.option_add("*Listbox.foreground", foreground)
        self.root.option_add("*Listbox.selectBackground", accent)
        self.root.option_add("*Listbox.selectForeground", foreground)
        self.root.option_add("*TCombobox*Listbox.background", field)
        self.root.option_add("*TCombobox*Listbox.foreground", foreground)
        self.root.option_add("*TCombobox*Listbox.selectBackground", accent)
        self.root.option_add("*TCombobox*Listbox.selectForeground", foreground)

    def _toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self._configure_dark_mode(ttk.Style(self.root))
        self.theme_toggle.configure(
            text="Switch to Light Mode" if self.dark_mode else "Switch to Dark Mode"
        )
        self._refresh_asset_colors()

    def _refresh_asset_colors(self):
        for tree in self.asset_trees.values():
            installed = "#45b86b" if self.dark_mode else "#18753b"
            missing = "#ff6b65" if self.dark_mode else "#a12622"
            tree.tag_configure("installed", foreground=installed)
            tree.tag_configure("missing", foreground=missing)
            tree.tag_configure("unconfigured", foreground=missing)

        installed = "#45b86b" if self.dark_mode else "#18753b"
        missing = "#ff6b65" if self.dark_mode else "#a12622"
        self.preset_members.tag_configure("installed", foreground=installed)
        self.preset_members.tag_configure("missing", foreground=missing)
        self.preset_members.tag_configure("unconfigured", foreground=missing)

        for widget in self._walk_widgets(self.root):
            if isinstance(widget, tk.Text):
                widget.configure(
                    background="#17181a" if self.dark_mode else "#ffffff",
                    foreground="#e8eaed" if self.dark_mode else "#202124",
                    insertbackground="#e8eaed" if self.dark_mode else "#202124",
                    selectbackground="#3c7dd9" if self.dark_mode else "#2f6fca",
                    selectforeground="#e8eaed" if self.dark_mode else "#ffffff",
                )
            elif isinstance(widget, tk.Listbox):
                widget.configure(
                    background="#17181a" if self.dark_mode else "#ffffff",
                    foreground="#e8eaed" if self.dark_mode else "#202124",
                    selectbackground="#3c7dd9" if self.dark_mode else "#2f6fca",
                    selectforeground="#e8eaed" if self.dark_mode else "#ffffff",
                )

        for index, name in enumerate(self.preset_lora_names):
            item = self.asset_entries["loras"].get(name)
            self.preset_lora_list.itemconfigure(index, foreground=self._asset_color(item))
        self._refresh_checkpoint_statuses()

    @staticmethod
    def _walk_widgets(parent):
        for child in parent.winfo_children():
            yield child
            yield from ThemeMixin._walk_widgets(child)
