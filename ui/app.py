"""Application coordinator for the Kama Card Builder desktop UI."""

import queue
import tkinter as tk
from tkinter import ttk

import generation
from services.config_store import _ensure_local_config
from ui.comfyui import ComfyUIMixin
from ui.card_creation import CardCreationMixin
from ui.generation_controls import GenerationControlsMixin
from ui.lora_presets import LoraPresetsMixin
from ui.models import ModelCatalogMixin
from ui.setup import SetupMixin
from ui.theme import ThemeMixin
from ui.constants import DEFAULT_GENERATE_FILE, PATHS_FILE, ROOT


class CardBuilderUI(
    ThemeMixin,
    SetupMixin,
    ComfyUIMixin,
    CardCreationMixin,
    LoraPresetsMixin,
    ModelCatalogMixin,
    GenerationControlsMixin,
):
    def __init__(self, root):
        self.root = root
        self.root.title("Kama Card Builder")
        self.root.geometry("1000x1000")
        self.root.minsize(720, 760)
        self.dark_mode = True
        style = ttk.Style(root)
        self._configure_dark_mode(style)
        style.configure("Comfy.Online.TLabel", foreground="#18753b")
        style.configure("Comfy.Offline.TLabel", foreground="#a12622")
        style.configure("Comfy.Unknown.TLabel", foreground="#8a5b00")
        self.messages = queue.Queue()
        self.path_entries = {}
        self.generate_file = tk.StringVar(value=str(DEFAULT_GENERATE_FILE))
        self.checkpoint_selection = tk.StringVar()
        self.depth_input = tk.StringVar()
        self.depth_output = tk.StringVar(value=str(generation.DEPTH_OUTPUT_DIR))
        self.selected_count = tk.StringVar(value="0 sets selected")
        self.selected_preset_count = tk.StringVar(value="0 presets selected")
        self.preset_name = tk.StringVar()
        self.preset_weight = tk.StringVar(value="1.0")
        self.preset_clip = tk.StringVar(value="1.0")
        self.status = tk.StringVar(value="Ready")
        self.comfy_status = tk.StringVar(value="ComfyUI: checking...")
        self.launcher_file = tk.StringVar()
        self.launcher_files = []
        self.launcher_selectors = []
        self.launch_buttons = []
        self.comfy_status_labels = []
        self.comfy_check_in_progress = False
        self.action_buttons = []
        self.asset_entries = {"loras": {}, "checkpoints": {}}
        self.asset_trees = {}
        self.asset_details = {}
        self.asset_get_buttons = {}
        self.asset_put_buttons = {}
        self.preset_set_names = []
        self.preset_lora_names = []
        self.card_prompt_editors = {}
        self.model_type = tk.StringVar(value="checkpoint")
        self.model_key = tk.StringVar()
        self.model_file = tk.StringVar()

        self._build_ui()
        self._load_paths()
        self._load_sets()
        self._refresh_comfyui()
        self.root.after(100, self._read_messages)
        self.root.after(5000, self._schedule_comfyui_check)

    def _build_ui(self):
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container)
        header.pack(fill="x", pady=(0, 6))
        self.theme_toggle = ttk.Button(
            header,
            text="Switch to Light Mode",
            command=self._toggle_theme,
        )
        self.theme_toggle.pack(side="right")

        self.pages = ttk.Notebook(container)
        self.pages.pack(fill="both", expand=True)

        setup = ttk.Frame(self.pages, padding=12)
        depth = ttk.Frame(self.pages, padding=12)
        image = ttk.Frame(self.pages, padding=12)
        card_creation = ttk.Frame(self.pages, padding=12)
        local_models = ttk.Frame(self.pages, padding=12)
        lora_presets = ttk.Frame(self.pages, padding=12)
        self.pages.add(setup, text="Setup")
        self.pages.add(depth, text="Depth Generation")
        self.pages.add(image, text="Image Generation")
        self.pages.add(card_creation, text="Card Creation")
        self.pages.add(lora_presets, text="LoRA Presets")
        self.pages.add(local_models, text="Local Models")

        self.local_model_pages = ttk.Notebook(local_models)
        self.local_model_pages.pack(fill="both", expand=True)
        loras = ttk.Frame(self.local_model_pages, padding=12)
        checkpoints = ttk.Frame(self.local_model_pages, padding=12)
        add_model = ttk.Frame(self.local_model_pages, padding=12)
        self.local_model_pages.add(loras, text="LoRAs")
        self.local_model_pages.add(checkpoints, text="Checkpoints")
        self.local_model_pages.add(add_model, text="Add Model")

        self._build_setup_page(setup)
        self._build_depth_page(depth)
        self._build_image_page(image)
        self._build_card_creation_page(card_creation)
        self._build_asset_page(loras, "loras")
        self._build_asset_page(checkpoints, "checkpoints")
        self._build_add_model_page(add_model)
        self._build_lora_presets_page(lora_presets)

        status_row = ttk.Frame(container)
        status_row.pack(fill="x", pady=(10, 4))
        ttk.Label(status_row, textvariable=self.status).pack(side="left")
        ttk.Label(status_row, text="Run output").pack(side="right")

        output_frame = ttk.Frame(container)
        output_frame.pack(fill="both", expand=True)
        self.output = tk.Text(output_frame, height=12, wrap="word", state="disabled")
        self.output.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(output_frame, command=self.output.yview)
        self.output.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

    def _read_messages(self):
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "output":
                    self._append_output(value)
                elif kind == "comfy-status":
                    running, text = value
                    self.comfy_check_in_progress = False
                    self.comfy_status.set(text)
                    style = (
                        "Comfy.Online.TLabel"
                        if running
                        else "Comfy.Offline.TLabel"
                    )
                    for label in self.comfy_status_labels:
                        label.configure(style=style)
                elif kind == "finished":
                    self.status.set(
                        "Finished successfully" if value == 0 else f"Failed (exit code {value})"
                    )
                    for button in self.action_buttons:
                        button.configure(state="normal")
                elif kind == "error":
                    self.status.set("Could not start generation")
                    self._append_output(f"ERROR: {value}\n")
                    for button in self.action_buttons:
                        button.configure(state="normal")
        except queue.Empty:
            pass
        self.root.after(100, self._read_messages)

    def _append_output(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")


def main():
    root = tk.Tk()
    try:
        _ensure_local_config(PATHS_FILE, ROOT / "paths.example.yaml")
        _ensure_local_config(DEFAULT_GENERATE_FILE, ROOT / "generate.example.yaml")
    except OSError as error:
        from tkinter import messagebox

        messagebox.showerror("Could not create local configuration", str(error))
        root.destroy()
        return
    CardBuilderUI(root)
    root.mainloop()
