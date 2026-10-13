"""ComfyUI status checks and launcher controls."""

import os
import subprocess
import threading
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import urlparse
from urllib.request import urlopen

import generation
from ui.constants import ROOT


class ComfyUIMixin:
    def _add_comfyui_controls(self, page):
        controls = ttk.LabelFrame(page, text="ComfyUI", padding=8)
        controls.pack(fill="x", pady=(0, 12))
        status_label = ttk.Label(
            controls,
            textvariable=self.comfy_status,
            style="Comfy.Unknown.TLabel",
        )
        status_label.pack(side="left")
        self.comfy_status_labels.append(status_label)
        ttk.Button(
            controls, text="Check now", command=self._refresh_comfyui
        ).pack(side="left", padx=(8, 0))
        ttk.Label(controls, text="Launcher").pack(side="left", padx=(16, 4))
        launcher_selector = ttk.Combobox(
            controls, textvariable=self.launcher_file, state="readonly", width=38
        )
        launcher_selector.pack(side="left", fill="x", expand=True)
        self.launcher_selectors.append(launcher_selector)
        ttk.Button(
            controls, text="Find .bat files", command=self._find_comfyui_launchers
        ).pack(side="left", padx=(8, 0))
        launch_button = ttk.Button(
            controls, text="Launch ComfyUI", command=self._launch_comfyui
        )
        launch_button.pack(side="left", padx=(8, 0))
        self.launch_buttons.append(launch_button)

    def _schedule_comfyui_check(self):
        self._refresh_comfyui()
        self.root.after(5000, self._schedule_comfyui_check)

    def _refresh_comfyui(self):
        if self.comfy_check_in_progress:
            return
        try:
            raw_paths = self._raw_ui_paths()
            url = generation.expand_vars(
                raw_paths.get("comfyui_url", ""),
                raw_paths,
                label="paths.local.yaml",
            ).strip().rstrip("/")
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise generation.ConfigError(
                    "Setup must contain a valid HTTP or HTTPS comfyui_url."
                )
        except (generation.ConfigError, OSError, ValueError) as error:
            self._set_comfyui_status(False, f"ComfyUI: not reachable ({error})")
            return

        self.comfy_check_in_progress = True
        self.comfy_status.set("ComfyUI: checking...")
        for label in self.comfy_status_labels:
            label.configure(style="Comfy.Unknown.TLabel")
        threading.Thread(
            target=self._check_comfyui_connection,
            args=(url,),
            daemon=True,
        ).start()

    def _check_comfyui_connection(self, url):
        try:
            with urlopen(f"{url}/system_stats", timeout=2) as response:
                if response.status != 200:
                    raise OSError(
                        f"ComfyUI returned HTTP status {response.status}"
                    )
            self.messages.put(("comfy-status", (True, "ComfyUI: running")))
        except (generation.ConfigError, OSError, ValueError) as error:
            self.messages.put(("comfy-status", (False, f"ComfyUI: not reachable ({error})")))

    def _set_comfyui_status(self, running, text):
        self.comfy_status.set(text)
        style = "Comfy.Online.TLabel" if running else "Comfy.Offline.TLabel"
        for label in self.comfy_status_labels:
            label.configure(style=style)

    def _find_comfyui_launchers(self, show_errors=True):
        try:
            raw_paths = self._raw_ui_paths()
            root_text = generation.expand_vars(
                raw_paths.get("comfyui_root", ""),
                raw_paths,
                label="paths.local.yaml",
            )
            if not root_text:
                raise generation.ConfigError("Setup must define 'comfyui_root'.")
            comfyui_root = Path(root_text).expanduser()
            if not comfyui_root.is_absolute():
                comfyui_root = ROOT / comfyui_root
            search_directories = [comfyui_root]
            search_directories.extend(list(comfyui_root.parents)[:3])
            found = set()
            for directory in search_directories:
                if not directory.is_dir():
                    continue
                for path in directory.glob("*.bat"):
                    if path.is_file() and (
                        "run" in path.stem.lower() or "comfy" in path.stem.lower()
                    ):
                        found.add(path.resolve())
            self.launcher_files = sorted(found, key=lambda path: str(path).lower())
        except (generation.ConfigError, OSError, ValueError) as error:
            self.launcher_files = []
            if show_errors:
                messagebox.showerror("Could not find ComfyUI launchers", str(error))

        values = [path.name for path in self.launcher_files]
        for selector in self.launcher_selectors:
            selector.configure(values=values)
        if self.launcher_file.get() not in values:
            self.launcher_file.set(values[0] if values else "")
        for button in self.launch_buttons:
            button.configure(
                state="normal" if values and os.name == "nt" else "disabled"
            )
        if show_errors and not values:
            messagebox.showinfo(
                "No ComfyUI launcher found",
                "No run*.bat or *comfy*.bat file was found in the ComfyUI folder or its nearby parent folders.",
            )

    def _launch_comfyui(self):
        selected_name = self.launcher_file.get()
        selected = next(
            (path for path in self.launcher_files if path.name == selected_name),
            None,
        )
        if selected is None or not selected.is_file():
            messagebox.showerror(
                "ComfyUI launcher unavailable",
                "Find or select a valid ComfyUI .bat launcher first.",
            )
            self._find_comfyui_launchers(show_errors=False)
            return
        if os.name != "nt":
            messagebox.showerror(
                "Unsupported launcher",
                "Batch-file launching is currently available only on Windows.",
            )
            return
        try:
            subprocess.Popen(
                ["cmd.exe", "/c", "call", str(selected)],
                cwd=selected.parent,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except OSError as error:
            messagebox.showerror("Could not launch ComfyUI", str(error))
            return
        self.status.set(f"Started ComfyUI using {selected.name}")
        self._append_output(f"> Launching ComfyUI: {selected}\n")
        self.root.after(3000, self._refresh_comfyui)
