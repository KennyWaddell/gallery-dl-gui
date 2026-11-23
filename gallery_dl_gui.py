#!/usr/bin/env python3
"""Interfaz grafica ligera (Tkinter) para gallery-dl en Linux."""

import json
import os
import shlex
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk


DEFAULT_DEST = os.path.expanduser("~/Imágenes")
if not os.path.isdir(DEFAULT_DEST):
    DEFAULT_DEST = os.path.expanduser("~/Descargas")
DEFAULT_ARCHIVE = os.path.expanduser("~/.local/share/gallery-dl-archivo.txt")
CONFIG_PATH = os.path.expanduser("~/.config/gallery-dl-gui.json")

THEMES = {
    "dark": {
        "bg": "#1e1e2e",
        "fg": "#e2e8f0",
        "panel": "#262637",
        "input_bg": "#141420",
        "input_fg": "#f8fafc",
        "btn_bg": "#334155",
        "btn_active": "#475569",
        "select_bg": "#3b82f6",
        "border": "#3f3f56",
        "tab_bg": "#262637",
        "tab_active": "#334155",
    },
    "light": {
        "bg": "#f1f5f9",
        "fg": "#0f172a",
        "panel": "#e2e8f0",
        "input_bg": "#ffffff",
        "input_fg": "#0f172a",
        "btn_bg": "#cbd5e1",
        "btn_active": "#94a3b8",
        "select_bg": "#2563eb",
        "border": "#cbd5e1",
        "tab_bg": "#e2e8f0",
        "tab_active": "#ffffff",
    },
}

FILETYPE_FILTERS = {
    "Todos": None,
    "Solo imágenes (jpg, png, webp, gif...)": "(extension or '').lower() in ('jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'avif')",
    "Solo imágenes sin GIF": "(extension or '').lower() in ('jpg', 'jpeg', 'png', 'webp', 'bmp', 'avif')",
    "Solo videos (mp4, webm, mkv...)": "(extension or '').lower() in ('mp4', 'webm', 'mkv', 'mov', 'm4v')",
}


def _select_all_entry(event: tk.Event) -> str:
    event.widget.selection_range(0, tk.END)
    event.widget.icursor(tk.END)
    return "break"


def _select_all_text(event: tk.Event) -> str:
    event.widget.tag_add(tk.SEL, "1.0", tk.END)
    event.widget.mark_set(tk.INSERT, "1.0")
    event.widget.see(tk.INSERT)
    return "break"


class GalleryDLGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Gallery-DL GUI")
        self.root.geometry("880x680")
        self.root.minsize(820, 600)

        self.process: subprocess.Popen | None = None
        self.processed_count = 0
        self.prefs = self._load_prefs()
        self.theme_name = self.prefs.get("theme", "dark")

        self.style = ttk.Style(self.root)
        self.style.theme_use("clam")

        self.root.bind_class("TEntry", "<Control-a>", _select_all_entry)
        self.root.bind_class("TEntry", "<Control-A>", _select_all_entry)
        self.root.bind_class("Text", "<Control-a>", _select_all_text)
        self.root.bind_class("Text", "<Control-A>", _select_all_text)

        self._context_target: tk.Widget | None = None
        self._build_context_menu()
        self._build_ui()
        self._apply_theme(self.theme_name)
        self._check_binary()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_context_menu(self) -> None:
        self.ctx_menu = tk.Menu(self.root, tearoff=0)
        self.ctx_menu.add_command(label="Cortar", command=lambda: self._ctx_event("<<Cut>>"))
        self.ctx_menu.add_command(label="Copiar", command=lambda: self._ctx_event("<<Copy>>"))
        self.ctx_menu.add_command(label="Pegar", command=lambda: self._ctx_event("<<Paste>>"))
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="Seleccionar todo", command=self._ctx_select_all)

        self.root.bind_class("TEntry", "<Button-3>", self._show_context_menu)
        self.root.bind_class("Text", "<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event: tk.Event) -> None:
        self._context_target = event.widget
        self.ctx_menu.tk_popup(event.x_root, event.y_root)

    def _ctx_event(self, virtual_ev: str) -> None:
        if self._context_target is not None:
            self._context_target.focus_set()
            self._context_target.event_generate(virtual_ev)

    def _ctx_select_all(self) -> None:
        w = self._context_target
        if isinstance(w, tk.Text):
            w.tag_add(tk.SEL, "1.0", tk.END)
        elif isinstance(w, ttk.Entry):
            w.selection_range(0, tk.END)
            w.icursor(tk.END)

    def _load_prefs(self) -> dict:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_prefs(self) -> None:
        data = {
            "theme": self.theme_name,
            "dest": self.dest_var.get().strip() or DEFAULT_DEST,
            "dir_mode": self.dir_mode.get(),
            "sleep": self.sleep_var.get().strip(),
            "min_size": self.min_size_var.get().strip(),
            "max_size": self.max_size_var.get().strip(),
            "limit_rate": self.rate_var.get().strip(),
            "retries": self.retries_var.get().strip(),
            "proxy": self.proxy_var.get().strip(),
            "date_after": self.date_after_var.get().strip(),
            "abort_count": self.abort_var.get().strip(),
            "filename_fmt": self.filename_var.get().strip(),
            "sleep_429": self.sleep_429_var.get().strip(),
            "no_skip": self.no_skip_var.get(),
            "write_pages": self.write_pages_var.get(),
            "browser": self.browser_var.get(),
            "archive": self.archive_var.get(),
            "verbose": self.verbose_var.get(),
            "metadata": self.metadata_var.get(),
            "filetype": self.filetype_var.get(),
        }
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _check_binary(self) -> None:
        path = shutil.which("gallery-dl")
        if not path:
            self._append_log(
                "[Aviso] No se encontro 'gallery-dl' en el PATH.\n"
                "Instalalo antes de descargar (por ejemplo: pip3 install --user gallery-dl).\n\n"
            )

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # --- Origen siempre visible arriba ---
        src_frame = ttk.LabelFrame(main, text="Origen (URL o lista .txt)", padding=8)
        src_frame.pack(fill=tk.X, **pad)

        self.input_mode = tk.StringVar(value="url")
        ttk.Radiobutton(src_frame, text="URL", variable=self.input_mode, value="url").grid(
            row=0, column=0, sticky=tk.W
        )
        ttk.Radiobutton(src_frame, text="Archivo de URLs (-i)", variable=self.input_mode, value="file").grid(
            row=0, column=1, sticky=tk.W, padx=(10, 0)
        )

        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(src_frame, textvariable=self.url_var)
        self.url_entry.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(6, 0))
        ttk.Button(src_frame, text="Pegar", command=self._paste_url).grid(
            row=1, column=2, padx=(6, 0), pady=(6, 0)
        )
        ttk.Button(src_frame, text="Limpiar", command=lambda: self.url_var.set("")).grid(
            row=1, column=3, padx=(6, 0), pady=(6, 0)
        )
        ttk.Button(src_frame, text="Elegir .txt...", command=self._pick_url_file).grid(
            row=1, column=4, padx=(6, 0), pady=(6, 0)
        )
        src_frame.columnconfigure(1, weight=1)

        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill=tk.X, **pad)

        basic_tab = ttk.Frame(self.notebook, padding=6)
        adv_tab = ttk.Frame(self.notebook, padding=6)
        help_tab = ttk.Frame(self.notebook, padding=6)
        credits_tab = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(basic_tab, text="Principal")
        self.notebook.add(adv_tab, text="Avanzado")
        self.notebook.add(help_tab, text="Ayuda")
        self.notebook.add(credits_tab, text="Créditos")

        self._build_basic_tab(basic_tab, pad)
        self._build_advanced_tab(adv_tab, pad)
        self._build_help_tab(help_tab, pad)
        self._build_credits_tab(credits_tab, pad)

        # --- Botones de accion ---
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, **pad)

        self.run_btn = ttk.Button(btn_frame, text="Ejecutar", command=self._start)
        self.run_btn.pack(side=tk.LEFT)

        self.stop_btn = ttk.Button(btn_frame, text="Detener", command=self._stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(6, 0))

        ttk.Button(btn_frame, text="Copiar comando", command=self._copy_command).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        self.theme_btn = ttk.Button(btn_frame, text="Modo claro", command=self._toggle_theme)
        self.theme_btn.pack(side=tk.RIGHT, padx=(6, 0))

        ttk.Button(btn_frame, text="Limpiar salida", command=self._clear_log).pack(side=tk.RIGHT)

        # --- Consola en vivo ---
        log_frame = ttk.LabelFrame(main, text="Salida en vivo", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True, **pad)

        self.log = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=12, state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True)

        # --- Barra de estado ---
        status_frame = ttk.Frame(main)
        status_frame.pack(fill=tk.X, padx=8, pady=(2, 0))
        self.status_var = tk.StringVar(value="Estado: Listo")
        self.count_var = tk.StringVar(value="Elementos: 0")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side=tk.LEFT)
        ttk.Label(status_frame, textvariable=self.count_var).pack(side=tk.RIGHT)

    def _build_basic_tab(self, parent: ttk.Frame, pad: dict) -> None:
        # --- Destino ---
        dst_frame = ttk.LabelFrame(parent, text="Carpeta de destino", padding=8)
        dst_frame.pack(fill=tk.X, **pad)

        self.dest_var = tk.StringVar(value=self.prefs.get("dest", DEFAULT_DEST))
        ttk.Entry(dst_frame, textvariable=self.dest_var).grid(row=0, column=0, sticky=tk.EW)
        ttk.Button(dst_frame, text="Examinar...", command=self._pick_dest_dir).grid(
            row=0, column=1, padx=(6, 0)
        )
        ttk.Button(dst_frame, text="Abrir carpeta", command=self._open_dest_dir).grid(
            row=0, column=2, padx=(6, 0)
        )

        self.dir_mode = tk.StringVar(value=self.prefs.get("dir_mode", "-d"))
        dir_opts = ttk.Frame(dst_frame)
        dir_opts.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(6, 0))
        ttk.Radiobutton(
            dir_opts, text="Crear subcarpetas por sitio/autor (-d)", variable=self.dir_mode, value="-d"
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            dir_opts, text="Guardar directo en esta carpeta (-D)", variable=self.dir_mode, value="-D"
        ).pack(side=tk.LEFT, padx=(18, 0))
        dst_frame.columnconfigure(0, weight=1)

        # --- Opciones frecuentes ---
        opt_frame = ttk.LabelFrame(parent, text="Opciones más usadas", padding=8)
        opt_frame.pack(fill=tk.X, **pad)

        ttk.Label(opt_frame, text="Rango (--range):").grid(row=0, column=0, sticky=tk.W)
        self.range_var = tk.StringVar()
        ttk.Entry(opt_frame, textvariable=self.range_var, width=12).grid(
            row=0, column=1, sticky=tk.W, padx=(4, 12)
        )

        ttk.Label(opt_frame, text="Pausa (--sleep):").grid(row=0, column=2, sticky=tk.W)
        self.sleep_var = tk.StringVar(value=self.prefs.get("sleep", "1-2"))
        ttk.Entry(opt_frame, textvariable=self.sleep_var, width=8).grid(
            row=0, column=3, sticky=tk.W, padx=(4, 12)
        )

        ttk.Label(opt_frame, text="Tamaño mín:").grid(row=0, column=4, sticky=tk.W)
        self.min_size_var = tk.StringVar(value=self.prefs.get("min_size", ""))
        ttk.Entry(opt_frame, textvariable=self.min_size_var, width=8).grid(
            row=0, column=5, sticky=tk.W, padx=(4, 4)
        )
        ttk.Label(opt_frame, text="ej. 50k").grid(row=0, column=6, sticky=tk.W)

        ttk.Label(opt_frame, text="Cookies navegador:").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        self.browser_var = tk.StringVar(value=self.prefs.get("browser", "ninguno"))
        ttk.Combobox(
            opt_frame,
            textvariable=self.browser_var,
            values=["ninguno", "firefox", "chromium", "chrome", "brave", "edge"],
            state="readonly",
            width=11,
        ).grid(row=1, column=1, sticky=tk.W, padx=(4, 12), pady=(6, 0))

        self.archive_var = tk.BooleanVar(value=self.prefs.get("archive", True))
        ttk.Checkbutton(
            opt_frame,
            text="Evitar duplicados (--download-archive)",
            variable=self.archive_var,
        ).grid(row=1, column=2, columnspan=5, sticky=tk.W, pady=(6, 0))

        ttk.Label(opt_frame, text="Tipo de archivo:").grid(row=2, column=0, sticky=tk.W, pady=(6, 0))
        legacy_ft = {
            "Solo imagenes (jpg, png, webp, gif...)": "Solo imágenes (jpg, png, webp, gif...)",
            "Solo imagenes sin GIF": "Solo imágenes sin GIF",
        }
        saved_ft = legacy_ft.get(self.prefs.get("filetype", "Todos"), self.prefs.get("filetype", "Todos"))
        if saved_ft not in FILETYPE_FILTERS:
            saved_ft = "Todos"
        self.filetype_var = tk.StringVar(value=saved_ft)
        ttk.Combobox(
            opt_frame,
            textvariable=self.filetype_var,
            values=list(FILETYPE_FILTERS.keys()),
            state="readonly",
            width=36,
        ).grid(row=2, column=1, columnspan=3, sticky=tk.W, padx=(4, 12), pady=(6, 0))

        ttk.Label(opt_frame, text="Álbumes (--child-range):").grid(row=2, column=4, sticky=tk.W, pady=(6, 0))
        self.child_range_var = tk.StringVar()
        ttk.Entry(opt_frame, textvariable=self.child_range_var, width=8).grid(
            row=2, column=5, sticky=tk.W, padx=(4, 4), pady=(6, 0)
        )
        ttk.Label(opt_frame, text="ej. 1-5").grid(row=2, column=6, sticky=tk.W, pady=(6, 0))

        ttk.Label(opt_frame, text="Modo:").grid(row=3, column=0, sticky=tk.W, pady=(6, 0))
        self.run_mode = tk.StringVar(value="download")
        mode_box = ttk.Frame(opt_frame)
        mode_box.grid(row=3, column=1, columnspan=6, sticky=tk.W, pady=(6, 0))
        ttk.Radiobutton(mode_box, text="Descargar", variable=self.run_mode, value="download").pack(side=tk.LEFT)
        ttk.Radiobutton(mode_box, text="Simular (-s)", variable=self.run_mode, value="simulate").pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Radiobutton(mode_box, text="URLs (-g)", variable=self.run_mode, value="urls").pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Radiobutton(mode_box, text="JSON (-j)", variable=self.run_mode, value="json").pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Radiobutton(mode_box, text="Variables (-K)", variable=self.run_mode, value="keywords").pack(
            side=tk.LEFT, padx=(8, 0)
        )
        self.verbose_var = tk.BooleanVar(value=self.prefs.get("verbose", True))
        ttk.Checkbutton(
            mode_box,
            text="Detallado (-v)",
            variable=self.verbose_var,
        ).pack(side=tk.LEFT, padx=(12, 0))

    def _build_advanced_tab(self, parent: ttk.Frame, pad: dict) -> None:
        adv_frame = ttk.LabelFrame(parent, text="Control de red, límites y metadatos", padding=10)
        adv_frame.pack(fill=tk.X, **pad)

        ttk.Label(adv_frame, text="Tamaño máx (--filesize-max):").grid(row=0, column=0, sticky=tk.W)
        self.max_size_var = tk.StringVar(value=self.prefs.get("max_size", ""))
        ttk.Entry(adv_frame, textvariable=self.max_size_var, width=12).grid(
            row=0, column=1, sticky=tk.W, padx=(6, 16)
        )
        ttk.Label(adv_frame, text="ej. 20M").grid(row=0, column=2, sticky=tk.W, padx=(0, 16))

        ttk.Label(adv_frame, text="Límite velocidad (-r):").grid(row=0, column=3, sticky=tk.W)
        self.rate_var = tk.StringVar(value=self.prefs.get("limit_rate", ""))
        ttk.Entry(adv_frame, textvariable=self.rate_var, width=12).grid(
            row=0, column=4, sticky=tk.W, padx=(6, 8)
        )
        ttk.Label(adv_frame, text="ej. 2M o 500k").grid(row=0, column=5, sticky=tk.W)

        ttk.Label(adv_frame, text="Reintentos (-R):").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        self.retries_var = tk.StringVar(value=self.prefs.get("retries", ""))
        ttk.Entry(adv_frame, textvariable=self.retries_var, width=12).grid(
            row=1, column=1, sticky=tk.W, padx=(6, 16), pady=(8, 0)
        )

        ttk.Label(adv_frame, text="Rango posts (--post-range):").grid(row=1, column=3, sticky=tk.W, pady=(8, 0))
        self.post_range_var = tk.StringVar()
        ttk.Entry(adv_frame, textvariable=self.post_range_var, width=12).grid(
            row=1, column=4, sticky=tk.W, padx=(6, 8), pady=(8, 0)
        )
        ttk.Label(adv_frame, text="ej. 1-10").grid(row=1, column=5, sticky=tk.W, pady=(8, 0))

        self.metadata_var = tk.BooleanVar(value=self.prefs.get("metadata", False))
        ttk.Checkbutton(
            adv_frame,
            text="Guardar metadatos en JSON (--write-metadata)",
            variable=self.metadata_var,
        ).grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(8, 0))

        self.no_skip_var = tk.BooleanVar(value=self.prefs.get("no_skip", False))
        ttk.Checkbutton(
            adv_frame,
            text="Sobrescribir existentes (--no-skip)",
            variable=self.no_skip_var,
        ).grid(row=2, column=3, columnspan=3, sticky=tk.W, pady=(8, 0))

        ttk.Label(adv_frame, text="Proxy (--proxy):").grid(row=3, column=0, sticky=tk.W, pady=(8, 0))
        self.proxy_var = tk.StringVar(value=self.prefs.get("proxy", ""))
        ttk.Entry(adv_frame, textvariable=self.proxy_var, width=24).grid(
            row=3, column=1, columnspan=2, sticky=tk.W, padx=(6, 16), pady=(8, 0)
        )

        ttk.Label(adv_frame, text="Desde fecha (--date-after):").grid(row=3, column=3, sticky=tk.W, pady=(8, 0))
        self.date_after_var = tk.StringVar(value=self.prefs.get("date_after", ""))
        ttk.Entry(adv_frame, textvariable=self.date_after_var, width=12).grid(
            row=3, column=4, sticky=tk.W, padx=(6, 8), pady=(8, 0)
        )
        ttk.Label(adv_frame, text="YYYY-MM-DD").grid(row=3, column=5, sticky=tk.W, pady=(8, 0))

        ttk.Label(adv_frame, text="Parar tras N omitidos (-A):").grid(row=4, column=0, sticky=tk.W, pady=(8, 0))
        self.abort_var = tk.StringVar(value=self.prefs.get("abort_count", ""))
        ttk.Entry(adv_frame, textvariable=self.abort_var, width=12).grid(
            row=4, column=1, sticky=tk.W, padx=(6, 16), pady=(8, 0)
        )

        ttk.Label(adv_frame, text="Formato nombre (-f):").grid(row=4, column=3, sticky=tk.W, pady=(8, 0))
        self.filename_var = tk.StringVar(value=self.prefs.get("filename_fmt", ""))
        ttk.Entry(adv_frame, textvariable=self.filename_var, width=22).grid(
            row=4, column=4, columnspan=2, sticky=tk.W, padx=(6, 0), pady=(8, 0)
        )

        ttk.Label(adv_frame, text="Espera 429 (--sleep-429):").grid(row=5, column=0, sticky=tk.W, pady=(8, 0))
        self.sleep_429_var = tk.StringVar(value=self.prefs.get("sleep_429", ""))
        ttk.Entry(adv_frame, textvariable=self.sleep_429_var, width=12).grid(
            row=5, column=1, sticky=tk.W, padx=(6, 16), pady=(8, 0)
        )
        ttk.Label(adv_frame, text="seg").grid(row=5, column=2, sticky=tk.W, pady=(8, 0))

        self.write_pages_var = tk.BooleanVar(value=self.prefs.get("write_pages", False))
        ttk.Checkbutton(
            adv_frame,
            text="Guardar páginas debug (--write-pages)",
            variable=self.write_pages_var,
        ).grid(row=5, column=3, columnspan=3, sticky=tk.W, pady=(8, 0))

        # --- Mantenimiento ---
        maint_frame = ttk.LabelFrame(parent, text="Mantenimiento de gallery-dl", padding=10)
        maint_frame.pack(fill=tk.X, **pad)

        ttk.Button(maint_frame, text="Comprobar versión", command=self._check_version).pack(side=tk.LEFT)
        ttk.Button(maint_frame, text="Actualizar gallery-dl", command=self._update_gallery_dl).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Label(
            maint_frame,
            text="Solo actualiza instalaciones de usuario (pip/pipx); no modifica configuraciones globales.",
        ).pack(side=tk.LEFT, padx=(12, 0))

    def _build_help_tab(self, parent: ttk.Frame, pad: dict) -> None:
        help_text = (
            "GUÍA DE USO PARA PRINCIPIANTES\n"
            "====================================================================\n\n"
            "¿Qué hace este programa?\n"
            "Descarga galerías completas de imágenes (y videos) desde cientos de\n"
            "páginas web pegando un enlace, sin tener que escribir comandos.\n\n"
            "1. PESTAÑA PRINCIPAL (lo que usarás casi siempre)\n"
            "--------------------------------------------------------------------\n"
            "• URL (arriba del todo): Pega aquí el enlace de la página o perfil.\n"
            "  Ejemplo: https://sitio.com/galeria\n\n"
            "• Archivo de URLs (-i): Si quieres bajar varias páginas seguidas,\n"
            "  crea un archivo .txt con un enlace por línea (sin comas) y selecciónalo.\n\n"
            "• Carpeta de destino:\n"
            "  - '-d' (Recomendado): Crea subcarpetas ordenadas por sitio y autor.\n"
            "  - '-D': Guarda todos los archivos directo en la carpeta elegida.\n\n"
            "• Rango (--range): Limita cuántas fotos bajar si una galería es grande.\n"
            "  Ejemplo: si hay 100 fotos y pones '1-10', solo descarga las 10 primeras.\n"
            "  Si pones '11-20', descarga de la 11 a la 20.\n\n"
            "• Álbumes (--child-range): Si pegas una categoría o búsqueda con varios\n"
            "  álbumes, limita cuántos álbumes bajar (ej. '1-5' baja solo 5 álbumes).\n\n"
            "• Pausa (--sleep): Segundos de espera entre foto y foto (ej. '1-2').\n"
            "  Evita que la página crea que eres un robot y te bloquee.\n\n"
            "• Tamaño mín: Evita bajar miniaturas borrosas o iconos de la web.\n"
            "  'k' significa Kilobytes y 'M' significa Megabytes.\n"
            "  Ejemplo: '50k' (50 KB) ignora iconos; '1M' (1 MB) solo baja archivos grandes.\n\n"
            "• Cookies navegador: Algunas webs (Instagram, X/Twitter, Pixiv) piden\n"
            "  iniciar sesión. Elige tu navegador donde ya tengas tu cuenta abierta.\n\n"
            "• Evitar duplicados: Recuerda lo que ya bajaste para no repetirlo.\n\n"
            "• Tipo de archivo: Elige 'Solo imágenes' si no quieres que se cuelen\n"
            "  videos .mp4, o 'Solo imágenes sin GIF' para bajar únicamente fotos.\n\n"
            "• Modo:\n"
            "  - Descargar: Baja los archivos a tu carpeta.\n"
            "  - Simular (-s): Prueba qué detecta la página sin descargar nada.\n"
            "  - URLs (-g): Solo muestra los enlaces directos de las imágenes.\n"
            "  - JSON (-j) / Variables (-K): Opciones técnicas para ver datos internos.\n"
            "  - Detallado (-v): Muestra paso a paso qué hace (útil si algo falla).\n\n"
            "2. PESTAÑA AVANZADO (opcional)\n"
            "--------------------------------------------------------------------\n"
            "• Tamaño máx (--filesize-max): Omite archivos más pesados que ese límite\n"
            "  (ej. '20M' = 20 Megabytes).\n"
            "• Límite velocidad (-r): Limita la velocidad de descarga para no saturar\n"
            "  tu internet (ej. '2M' = 2 MB/s, '500k' = 500 KB/s).\n"
            "• Reintentos (-R): Cuántas veces reintenta si falla tu conexión (ej. 5).\n"
            "• Rango posts (--post-range): En redes sociales, limita publicaciones.\n"
            "• Guardar metadatos JSON: Guarda un archivo .json con título, autor y fecha.\n"
            "• Sobrescribir (--no-skip): Vuelve a descargar archivos aunque ya existan.\n"
            "• Proxy (--proxy): Enruta la conexión por proxy o Tor (ej. socks5://127.0.0.1:9050).\n"
            "• Desde fecha (--date-after): Solo baja contenido posterior a esa fecha\n"
            "  en formato AÑO-MES-DÍA (ej. 2025-01-01).\n"
            "• Parar tras N omitidos (-A): Si ya bajaste un perfil antes, al encontrar N\n"
            "  archivos repetidos seguidos se detiene solo (ahorra mucho tiempo).\n"
            "• Formato nombre (-f): Cambia cómo se llaman los archivos al guardar.\n"
            "  Ejemplo: {num:>03}_{filename}.{extension}\n"
            "• Espera 429 (--sleep-429): El error 429 ocurre cuando una página te pide\n"
            "  ir más despacio. Pon '30' para que espere 30 segundos y siga solo.\n"
            "• Guardar páginas debug (--write-pages): Solo para programadores/depuración.\n"
        )
        self.help_box = scrolledtext.ScrolledText(parent, wrap=tk.WORD, height=16)
        self.help_box.pack(fill=tk.BOTH, expand=True, **pad)
        self.help_box.insert("1.0", help_text)
        self.help_box.configure(state=tk.DISABLED)

    def _build_credits_tab(self, parent: ttk.Frame, pad: dict) -> None:
        wrapper = ttk.Frame(parent, padding=16)
        wrapper.pack(fill=tk.BOTH, expand=True)

        card = ttk.LabelFrame(wrapper, text="Acerca del proyecto", padding=20)
        card.pack(expand=True, fill=tk.BOTH)

        ttk.Label(card, text="Gallery-DL GUI", font=("TkDefaultFont", 15, "bold")).pack(pady=(4, 2))
        ttk.Label(
            card,
            text="Interfaz gráfica ultraligera para Linux sin dependencias externas",
            font=("TkDefaultFont", 10, "italic"),
        ).pack(pady=(0, 12))

        ttk.Separator(card, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 14))

        info = ttk.Frame(card)
        info.pack()

        rows = [
            ("Autor:", "Kenny Waddell"),
            ("Licencia:", "GNU GPLv3 (Software Libre)"),
            ("Motor:", "gallery-dl (Python 3 + Tkinter)"),
            ("Repositorio:", "https://github.com/KennyWaddell/gallery-dl-gui"),
        ]
        for idx, (label, value) in enumerate(rows):
            ttk.Label(info, text=label, font=("TkDefaultFont", 10, "bold")).grid(
                row=idx, column=0, sticky=tk.E, padx=(0, 12), pady=3
            )
            ttk.Label(info, text=value).grid(row=idx, column=1, sticky=tk.W, pady=3)

        ttk.Button(
            card,
            text="Copiar enlace de GitHub",
            command=lambda: self._copy_text(
                "https://github.com/KennyWaddell/gallery-dl-gui",
                "Enlace de GitHub copiado al portapapeles",
            ),
        ).pack(pady=(16, 4))

    def _apply_theme(self, name: str) -> None:
        self.theme_name = name if name in THEMES else "dark"
        t = THEMES[self.theme_name]
        self.root.configure(bg=t["bg"])

        self.style.configure(".", background=t["bg"], foreground=t["fg"], bordercolor=t["border"])
        self.style.configure("TFrame", background=t["bg"])
        self.style.configure("TNotebook", background=t["bg"], bordercolor=t["border"])
        self.style.configure("TNotebook.Tab", background=t["tab_bg"], foreground=t["fg"], padding=[10, 4])
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", t["tab_active"])],
            foreground=[("selected", t["fg"])],
        )
        self.style.configure("TLabelframe", background=t["bg"], foreground=t["fg"])
        self.style.configure("TLabelframe.Label", background=t["bg"], foreground=t["fg"])
        self.style.configure("TLabel", background=t["bg"], foreground=t["fg"])
        self.style.configure("TRadiobutton", background=t["bg"], foreground=t["fg"])
        self.style.configure("TCheckbutton", background=t["bg"], foreground=t["fg"])
        self.style.map(
            "TRadiobutton",
            background=[("active", t["panel"])],
            foreground=[("active", t["fg"])],
        )
        self.style.map(
            "TCheckbutton",
            background=[("active", t["panel"])],
            foreground=[("active", t["fg"])],
        )
        self.style.configure("TButton", background=t["btn_bg"], foreground=t["fg"], padding=5)
        self.style.map(
            "TButton",
            background=[("active", t["btn_active"]), ("disabled", t["panel"])],
        )
        self.style.configure(
            "TEntry",
            fieldbackground=t["input_bg"],
            foreground=t["input_fg"],
            insertcolor=t["input_fg"],
        )
        self.style.configure(
            "TCombobox",
            fieldbackground=t["input_bg"],
            background=t["btn_bg"],
            foreground=t["input_fg"],
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", t["input_bg"])],
            foreground=[("readonly", t["input_fg"])],
            selectbackground=[("readonly", t["select_bg"])],
        )

        self.log.configure(
            bg=t["input_bg"],
            fg=t["input_fg"],
            insertbackground=t["input_fg"],
            selectbackground=t["select_bg"],
        )
        self.help_box.configure(
            bg=t["input_bg"],
            fg=t["input_fg"],
            selectbackground=t["select_bg"],
        )
        self.theme_btn.configure(text="Modo claro" if self.theme_name == "dark" else "Modo oscuro")

    def _toggle_theme(self) -> None:
        self._apply_theme("light" if self.theme_name == "dark" else "dark")
        self._save_prefs()

    def _paste_url(self) -> None:
        try:
            clip = self.root.clipboard_get().strip()
            if clip:
                self.url_var.set(clip)
        except tk.TclError:
            pass

    def _pick_url_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleccionar archivo con URLs",
            filetypes=[("Archivos de texto", "*.txt"), ("Todos", "*.*")],
        )
        if path:
            self.input_mode.set("file")
            self.url_var.set(path)

    def _pick_dest_dir(self) -> None:
        path = filedialog.askdirectory(title="Seleccionar carpeta de destino", initialdir=self.dest_var.get())
        if path:
            self.dest_var.set(path)

    def _open_dest_dir(self) -> None:
        dest = self.dest_var.get().strip() or DEFAULT_DEST
        os.makedirs(dest, exist_ok=True)
        subprocess.Popen(["xdg-open", dest], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)

    def _build_command(self) -> list[str] | None:
        target = self.url_var.get().strip()
        if not target:
            messagebox.showwarning("Falta origen", "Ingresa una URL o elige un archivo de URLs.")
            return None

        cmd = ["gallery-dl"]

        dest = self.dest_var.get().strip()
        if dest:
            cmd.extend([self.dir_mode.get(), dest])

        simple_opts = [
            ("--range", self.range_var.get()),
            ("--child-range", self.child_range_var.get()),
            ("--post-range", self.post_range_var.get()),
            ("--sleep", self.sleep_var.get()),
            ("--filesize-min", self.min_size_var.get()),
            ("--filesize-max", self.max_size_var.get()),
            ("-r", self.rate_var.get()),
            ("-R", self.retries_var.get()),
            ("--proxy", self.proxy_var.get()),
            ("--date-after", self.date_after_var.get()),
            ("-A", self.abort_var.get()),
            ("-f", self.filename_var.get()),
            ("--sleep-429", self.sleep_429_var.get()),
        ]
        for flag, val in simple_opts:
            cleaned = val.strip()
            if cleaned:
                cmd.extend([flag, cleaned])

        browser = self.browser_var.get()
        if browser and browser != "ninguno":
            cmd.extend(["--cookies-from-browser", browser])

        if self.archive_var.get():
            os.makedirs(os.path.dirname(DEFAULT_ARCHIVE), exist_ok=True)
            cmd.extend(["--download-archive", DEFAULT_ARCHIVE])

        if self.metadata_var.get():
            cmd.append("--write-metadata")

        if self.no_skip_var.get():
            cmd.append("--no-skip")

        if self.write_pages_var.get():
            cmd.append("--write-pages")

        flt = FILETYPE_FILTERS.get(self.filetype_var.get())
        if flt:
            cmd.extend(["--filter", flt])

        if self.verbose_var.get():
            cmd.append("-v")

        mode_flags = {
            "simulate": "-s",
            "urls": "-g",
            "json": "-j",
            "keywords": "-K",
        }
        flag = mode_flags.get(self.run_mode.get())
        if flag:
            cmd.append(flag)

        if self.input_mode.get() == "file":
            cmd.extend(["-i", target])
        else:
            cmd.extend(["--", target])

        return cmd

    def _copy_text(self, text: str, status_msg: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set(f"Estado: {status_msg}")

    def _copy_command(self) -> None:
        cmd = self._build_command()
        if cmd is None:
            return
        self._copy_text(shlex.join(cmd), "Comando copiado al portapapeles")

    def _start(self) -> None:
        if self.process is not None:
            return
        cmd = self._build_command()
        if cmd is None:
            return
        self._launch_process(cmd, label="Ejecutando...", count_items=True)

    def _launch_process(
        self,
        cmd: list[str],
        label: str,
        count_items: bool,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self._save_prefs()
        self.processed_count = 0
        self.count_var.set("Elementos: 0")
        self.status_var.set(f"Estado: {label}")
        self._append_log(f"$ {shlex.join(cmd)}\n\n")

        proc_env = {**os.environ, **extra_env} if extra_env else None
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=proc_env,
            )
        except FileNotFoundError:
            self._append_log("\n[Error: no se encontro el ejecutable]\n\n")
            self.status_var.set("Estado: Error")
            return
        except Exception as exc:
            self._append_log(f"\n[Error: {exc}]\n\n")
            self.status_var.set("Estado: Error")
            return

        self.run_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        threading.Thread(target=self._run_worker, args=(self.process, count_items), daemon=True).start()

    def _run_worker(self, proc: subprocess.Popen, count_items: bool) -> None:
        try:
            assert proc.stdout is not None
            with proc.stdout:
                for line in proc.stdout:
                    self.root.after(0, self._append_log, line)
                    if count_items:
                        stripped = line.strip()
                        if stripped and not stripped.startswith("[") and not stripped.startswith("#"):
                            self.processed_count += 1
                            self.root.after(0, self.count_var.set, f"Elementos: {self.processed_count}")
            code = proc.wait()
            self.root.after(0, self._append_log, f"\n[Finalizado con codigo {code}]\n\n")
            self.root.after(0, self.status_var.set, f"Estado: Listo (codigo {code})")
        except Exception as exc:
            self.root.after(0, self._append_log, f"\n[Error: {exc}]\n\n")
            self.root.after(0, self.status_var.set, "Estado: Error")
        finally:
            self.root.after(0, self._on_finished)

    def _on_finished(self) -> None:
        self.process = None
        self.run_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)

    def _stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            self._append_log("\n[Deteniendo proceso...]\n")
            self.status_var.set("Estado: Detenido")

    def _check_version(self) -> None:
        if self.process is not None:
            return
        self._launch_process(["gallery-dl", "--version"], label="Comprobando version...", count_items=False)

    def _update_gallery_dl(self) -> None:
        if self.process is not None:
            return
        bin_path = shutil.which("gallery-dl") or ""
        extra_env = None
        if "pipx" in bin_path and shutil.which("pipx"):
            cmd = ["pipx", "upgrade", "gallery-dl"]
        elif bin_path.startswith(os.path.expanduser("~/.local/")) and shutil.which("pip3"):
            cmd = ["pip3", "install", "--user", "-U", "gallery-dl"]
            extra_env = {"PIP_BREAK_SYSTEM_PACKAGES": "1"}
        else:
            self._append_log(
                f"[Aviso] gallery-dl esta instalado en '{bin_path or 'sistema'}'.\n"
                "Actualizalo con el gestor de paquetes de tu distro (ej. sudo apt update && sudo apt upgrade) "
                "para no interferir con paquetes del sistema.\n\n"
            )
            return

        if messagebox.askyesno("Actualizar gallery-dl", f"Se ejecutara:\n{shlex.join(cmd)}\n\nContinuar?"):
            self._launch_process(
                cmd,
                label="Actualizando gallery-dl...",
                count_items=False,
                extra_env=extra_env,
            )

    def _on_close(self) -> None:
        if self.process is not None:
            try:
                self.process.terminate()
            except OSError:
                pass
        self._save_prefs()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    GalleryDLGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
