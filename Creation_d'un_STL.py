# -*- coding: utf-8 -*-
"""
=============================================================
  CRÉATEUR D'UN STL EN 3D - Application unique
=============================================================
  - Aperçu en direct grand format
  - Luminosité / Contraste / Gamma / Flou (0 à 3)
  - Dossiers de destination pour l'image et le STL
  - Bouton OK pour tout enregistrer et générer le STL
  - Ouverture dans un logiciel externe (chemin mémorisé)
  - Panneau de gauche défilable si l'écran est petit

  Prérequis : pip install Pillow numpy numpy-stl
=============================================================
"""
import os
import sys
import json
import subprocess
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox

import numpy as np
from PIL import Image, ImageTk, ImageEnhance, ImageFilter

try:
    from stl import mesh as stl_mesh
    STL_OK = True
except ImportError:
    STL_OK = False
    # 2. Gestion des chemins pour PyInstaller (C'est CA qu'il fallait remplacer)
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE  = os.path.join(APP_DIR, "config_stl.json")
LOGO_PATH    = os.path.join(APP_DIR, "logo.png")


APP_DIR      = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE  = os.path.join(APP_DIR, "config_stl.json")
LOGO_PATH    = os.path.join(APP_DIR, "logo.png")

# Couleurs du thème clair
BG_MAIN      = "#f0f2f5"
BG_PANEL     = "#ffffff"
FG_TEXT      = "#333333"
FG_TITLE     = "#2c3e50"
FG_SUBTLE    = "#7f8c8d"
TROUGH_COLOR = "#dcdde1"

DEFAULTS = {
    "image_path"           : "",
    "corrected_image_path" : "",
    "stl_path"             : "",
    "diameter"             : 60.0,
    "z_height"             : 4.0,
    "base_epaisseur"       : 1.5,
    "resolution"           : 300,
    "brightness"           : 1.0,
    "contrast"             : 1.0,
    "gamma"                : 2.0,
    "blur"                 : 1.0,
    "external_software"    : "",
}


# ============================================================
#  CONFIG
# ============================================================
def load_config():
    cfg = DEFAULTS.copy()
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception as e:
            print(f"[CONFIG] Lecture impossible : {e}")
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[CONFIG] Ecriture impossible : {e}")


# ============================================================
#  TRAITEMENT IMAGE
# ============================================================
def load_and_prepare(image_path, resolution):
    img = Image.open(image_path).convert("L")
    arr = np.array(img)

    mask = arr > 15
    if mask.any():
        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)
        y_min, y_max = np.where(rows)[0][[0, -1]]
        x_min, x_max = np.where(cols)[0][[0, -1]]
        m = 2
        y_min = max(0, y_min - m)
        y_max = min(img.height - 1, y_max + m)
        x_min = max(0, x_min - m)
        x_max = min(img.width - 1, x_max + m)
        img = img.crop((x_min, y_min, x_max + 1, y_max + 1))

    w, h = img.size
    size = max(w, h)
    square = Image.new("L", (size, size), 0)
    square.paste(img, ((size - w) // 2, (size - h) // 2))
    return square.resize((resolution, resolution), Image.LANCZOS)


def apply_params(img_base, brightness, contrast, gamma, blur):
    if img_base is None:
        return None
    img = img_base.copy()

    if abs(brightness - 1.0) > 1e-3:
        img = ImageEnhance.Brightness(img).enhance(brightness)
    if abs(contrast - 1.0) > 1e-3:
        img = ImageEnhance.Contrast(img).enhance(contrast)
    if abs(gamma - 1.0) > 1e-3:
        arr = np.array(img, dtype=np.float32) / 255.0
        arr = np.clip(np.power(arr, gamma), 0.0, 1.0)
        img = Image.fromarray((arr * 255.0).astype(np.uint8))
    if blur > 0.05:
        img = img.filter(ImageFilter.GaussianBlur(radius=blur))
    return img


# ============================================================
#  GÉNÉRATION STL
# ============================================================
def generate_stl(img_processed, stl_path, diameter, base_epaisseur, z_height):
    arr = np.array(img_processed, dtype=np.float64) / 255.0
    res = arr.shape[0]
    step = diameter / (res - 1)

    xs = np.arange(res) * step
    ys = np.arange(res) * step
    X, Y = np.meshgrid(xs, ys, indexing="xy")
    Z = base_epaisseur + arr * z_height
    verts = np.stack([X, Y, Z], axis=-1)

    n = res - 1
    y_idx, x_idx = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")

    v00 = verts[y_idx,     x_idx    ]
    v10 = verts[y_idx + 1, x_idx    ]
    v01 = verts[y_idx,     x_idx + 1]
    v11 = verts[y_idx + 1, x_idx + 1]

    tri1 = np.stack([v00, v10, v01], axis=1)
    tri2 = np.stack([v10, v11, v01], axis=1)
    faces = np.concatenate([tri1, tri2], axis=0).astype(np.float32)

    num_faces = faces.shape[0]
    m = stl_mesh.Mesh(np.zeros(num_faces, dtype=stl_mesh.Mesh.dtype))
    m.vectors = faces
    m.save(stl_path)
    return num_faces


# ============================================================
#  CONTENEUR DÉFILABLE (pour la colonne de gauche)
# ============================================================
class ScrollableFrame(tk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        canvas = tk.Canvas(self, borderwidth=0, bg=BG_MAIN, highlightthickness=0)
        scrollbar = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg=BG_MAIN)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Gestion de la molette de la souris
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        self.bind_all("<MouseWheel>", _on_mousewheel)


# ============================================================
#  INTERFACE
# ============================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Créateur d'un STL en 3D")
        self.geometry("1150x850") # Taille réduite pour s'adapter aux écrans
        self.configure(bg=BG_MAIN)
        self.minsize(1000, 700)

        # Chargement du logo
        try:
            if os.path.isfile(LOGO_PATH):
                logo_img = Image.open(LOGO_PATH)
                logo_img.thumbnail((150, 10), Image.LANCZOS) # Légèrement réduit
                self.logo_photo = ImageTk.PhotoImage(logo_img)
                self.iconphoto(True, self.logo_photo)
            else:
                self.logo_photo = None
        except Exception as e:
            print(f"[LOGO] Impossible de charger : {e}")
            self.logo_photo = None

        self.cfg          = load_config()
        self._last_saved  = dict(self.cfg)

        self.img_base     = None
        self.img_processed= None
        self.photo        = None
        self._preview_job = None
        self._stl_path    = self.cfg.get("stl_path", "")

        self._build_ui()
        self._refresh_software_label()

        if self.cfg.get("image_path") and os.path.isfile(self.cfg["image_path"]):
            self.after(100, lambda: self._load_image(self.cfg["image_path"]))

        self.bind("<Escape>", lambda e: self.destroy())

    # --------------------------------------------------------
    def _build_ui(self):
        # Titre principal
        tk.Label(self, text="Créateur d'un STL en 3D",
                 font=("Segoe UI", 28, "bold"),
                 bg=BG_MAIN, fg=FG_TITLE).pack(pady=(15, 10))

        main = tk.Frame(self, bg=BG_MAIN)
        main.pack(fill="both", expand=True, padx=20, pady=0)
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        # --- Colonne de gauche (Défilable) ---
        self.left_scroll = ScrollableFrame(main, bg=BG_MAIN)
        self.left_scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
        left_frame = self.left_scroll.scrollable_frame
        
        # Logo centré
        if self.logo_photo:
            tk.Label(left_frame, image=self.logo_photo, bg=BG_MAIN).pack(pady=(0, 15))

        self._build_left(left_frame)

        # --- Colonne de droite (Aperçu) ---
        right_frame = tk.Frame(main, bg=BG_MAIN)
        right_frame.grid(row=0, column=1, sticky="nsew")
        self._build_right(right_frame)

        # --- Barre du bas (Fixée tout en bas) ---
        self._build_bottom()

    # ------------------------- GAUCHE ------------------------
    def _build_left(self, parent):
        f = parent

        # 1. Image à rectifier
        box_in = tk.LabelFrame(f, text="  Image à rectifier  ",
                            font=("Segoe UI", 11, "bold"),
                            bg=BG_MAIN, fg=FG_TITLE,
                            bd=1, relief="solid")
        box_in.pack(fill="x", pady=(0, 10))

        self.var_image = tk.StringVar(value=self.cfg.get("image_path", ""))
        tk.Entry(box_in, textvariable=self.var_image, font=("Consolas", 10),
                 bg="white", fg=FG_TEXT).pack(side="left", fill="x", expand=True, padx=8, pady=6)
                 
        tk.Button(box_in, text="Parcourir...", command=self._browse_image,
                  font=("Segoe UI", 10, "bold"),
                  bg="#4caf50", fg="white", bd=0, padx=10, pady=3,
                  cursor="hand2").pack(side="right", padx=8, pady=6)

        # 2. Image corrigée
        box_out = tk.LabelFrame(f, text="  Image corrigée (sortie)  ",
                            font=("Segoe UI", 11, "bold"),
                            bg=BG_MAIN, fg=FG_TITLE,
                            bd=1, relief="solid")
        box_out.pack(fill="x", pady=(0, 10))

        self.var_corrected_image_path = tk.StringVar(value=self.cfg.get("corrected_image_path", ""))
        tk.Entry(box_out, textvariable=self.var_corrected_image_path, font=("Consolas", 10),
                 bg="white", fg=FG_TEXT).pack(side="left", fill="x", expand=True, padx=8, pady=6)
                 
        tk.Button(box_out, text="Parcourir...", command=self._browse_corrected_image,
                  font=("Segoe UI", 10, "bold"),
                  bg="#4caf50", fg="white", bd=0, padx=10, pady=3,
                  cursor="hand2").pack(side="right", padx=8, pady=6)

        # 3. Destination STL
        box_stl = tk.LabelFrame(f, text="  Fichier STL de destination  ",
                            font=("Segoe UI", 11, "bold"),
                            bg=BG_MAIN, fg=FG_TITLE,
                            bd=1, relief="solid")
        box_stl.pack(fill="x", pady=(0, 10))

        self.var_stl_path = tk.StringVar(value=self.cfg.get("stl_path", ""))
        tk.Entry(box_stl, textvariable=self.var_stl_path, font=("Consolas", 10),
                 bg="white", fg=FG_TEXT).pack(side="left", fill="x", expand=True, padx=8, pady=6)
                 
        tk.Button(box_stl, text="Parcourir...", command=self._browse_stl,
                  font=("Segoe UI", 10, "bold"),
                  bg="#4caf50", fg="white", bd=0, padx=10, pady=3,
                  cursor="hand2").pack(side="right", padx=8, pady=6)

        # 4. Dimensions
        box2 = tk.LabelFrame(f, text="  Dimensions  ",
                             font=("Segoe UI", 11, "bold"),
                             bg=BG_MAIN, fg=FG_TITLE,
                             bd=1, relief="solid")
        box2.pack(fill="x", pady=(0, 10))
        box2.columnconfigure(1, weight=1)

        self.var_diameter = tk.StringVar(value=str(self.cfg["diameter"]))
        self.var_z        = tk.StringVar(value=str(self.cfg["z_height"]))
        self.var_base     = tk.StringVar(value=str(self.cfg["base_epaisseur"]))

        self._make_entry_row(box2, 0, "Diamètre (mm) :",       self.var_diameter)
        self._make_entry_row(box2, 1, "Hauteur Z (mm) :",      self.var_z)
        self._make_entry_row(box2, 2, "Socle / base (mm) :",   self.var_base)

        # 5. Paramètres image
        box3 = tk.LabelFrame(f, text="  Paramètres de l'image  ",
                             font=("Segoe UI", 11, "bold"),
                             bg=BG_MAIN, fg=FG_TITLE,
                             bd=1, relief="solid")
        box3.pack(fill="x", pady=(0, 15))
        box3.columnconfigure(1, weight=1)

        self.var_brightness = tk.DoubleVar(value=self.cfg["brightness"])
        self.var_contrast   = tk.DoubleVar(value=self.cfg["contrast"])
        self.var_gamma      = tk.DoubleVar(value=self.cfg["gamma"])
        self.var_blur       = tk.DoubleVar(value=self.cfg["blur"])

        self._make_slider_row(box3, 0, "Luminosité",   self.var_brightness, 0.3, 2.0, 0.05)
        self._make_slider_row(box3, 1, "Contraste",    self.var_contrast,   0.3, 2.5, 0.05)
        self._make_slider_row(box3, 2, "Gamma",        self.var_gamma,      0.5, 4.0, 0.1)
        self._make_slider_row(box3, 3, "Flou (rayon)", self.var_blur,       0.0, 3.0, 0.1)

        tk.Label(box3, text="💡 Flou = arrondit les pentes.\nGamma > 1 = gris moyens assombris.",
                 font=("Segoe UI", 9, "italic"),
                 bg=BG_MAIN, fg=FG_SUBTLE, justify="left",
                 anchor="w").grid(row=4, column=0, columnspan=3,
                                   sticky="w", padx=8, pady=(2, 8))

        # Bouton OK
        bar = tk.Frame(f, bg=BG_MAIN)
        bar.pack(fill="x", pady=(5, 15))
        tk.Button(bar, text="✓  OK — Enregistrer l'image",
                  command=self._save_and_create,
                  font=("Segoe UI", 11, "bold"),
                  bg="#4caf50", fg="white", bd=0,
                  padx=20, pady=8, cursor="hand2").pack(side="left")

    def _make_entry_row(self, parent, row, label, var):
        tk.Label(parent, text=label, font=("Segoe UI", 11),
                 bg=BG_MAIN, fg=FG_TEXT, anchor="w"
                 ).grid(row=row, column=0, sticky="w", padx=8, pady=4)
        tk.Entry(parent, textvariable=var, font=("Consolas", 11), width=10,
                 bg="white", fg=FG_TEXT
                 ).grid(row=row, column=1, sticky="w", padx=8, pady=4)

    def _make_slider_row(self, parent, row, label, var, mn, mx, step):
        tk.Label(parent, text=label, font=("Segoe UI", 11),
                 bg=BG_MAIN, fg=FG_TEXT, anchor="w"
                 ).grid(row=row, column=0, sticky="w", padx=8, pady=3)
        s = tk.Scale(parent, variable=var, from_=mn, to=mx, resolution=step,
                     orient="horizontal", bg=BG_MAIN, fg=FG_TEXT,
                     troughcolor=TROUGH_COLOR, highlightthickness=0,
                     length=180, font=("Consolas", 10),
                     command=lambda v: self._schedule_preview())
        s.grid(row=row, column=1, padx=5, pady=3, sticky="ew")
        tk.Label(parent, textvariable=var, font=("Consolas", 10, "bold"),
                 bg=BG_MAIN, fg="#e67e22", width=6
                 ).grid(row=row, column=2, padx=5)

    # ------------------------- DROITE ------------------------
    def _build_right(self, parent):
        f = parent

        tk.Label(f, text="APERÇU EN DIRECT",
                 font=("Segoe UI", 14, "bold"),
                 bg=BG_MAIN, fg=FG_TITLE).pack(pady=(0, 2))
        tk.Label(f, text="(blanc = sommet du relief, noir = creux)",
                 font=("Segoe UI", 10, "italic"),
                 bg=BG_MAIN, fg=FG_SUBTLE).pack(pady=(0, 8))

        self.preview_frame = tk.Frame(f, bg=BG_PANEL, bd=1, relief="solid")
        self.preview_frame.pack(fill="both", expand=True)
        self.preview_frame.pack_propagate(False)

        self.preview_label = tk.Label(self.preview_frame,
                                       text="Charge une image\npour voir l'aperçu",
                                       font=("Segoe UI", 14),
                                       bg=BG_PANEL, fg=FG_SUBTLE)
        self.preview_label.pack(fill="both", expand=True)
        self.preview_label.bind("<Configure>", lambda e: self._render_preview())

    # ------------------------- BAS ---------------------------
    def _build_bottom(self):
        bar = tk.Frame(self, bg=BG_MAIN)
        bar.pack(side="bottom", fill="x", padx=20, pady=15)

        tk.Button(bar, text="🔨   CRÉER LE STL",
                  command=self._create_stl,
                  font=("Segoe UI", 13, "bold"),
                  bg="#ff9800", fg="white", bd=0,
                  padx=20, pady=10, cursor="hand2"
                  ).pack(side="left", padx=(0, 10))

        self.btn_software = tk.Button(bar, text="⚙  Configurer le logiciel STL",
                                      command=self._choose_software,
                                      font=("Segoe UI", 11, "bold"),
                                      bg="#2196f3", fg="white", bd=0,
                                      padx=15, pady=10, cursor="hand2")
        self.btn_software.pack(side="left", padx=(0, 10))

        self.btn_open = tk.Button(bar, text="🚀  Ouvrir le STL",
                                  command=self._open_in_software,
                                  font=("Segoe UI", 11, "bold"),
                                  bg="#673ab7", fg="white", bd=0,
                                  padx=15, pady=10, cursor="hand2")
        self.btn_open.pack(side="left")

        self.lbl_status = tk.Label(bar, text="",
                                   font=("Segoe UI", 10, "italic"),
                                   bg=BG_MAIN, fg=FG_SUBTLE)
        self.lbl_status.pack(side="right", padx=10)

    # ========================================================
    #  GESTION FICHIERS
    # ========================================================
    def _browse_image(self):
        p = filedialog.askopenfilename(
            title="Choisis une image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp"),
                       ("Tous", "*.*")])
        if p:
            self._load_image(p)

    def _load_image(self, path):
        try:
            self.img_base = load_and_prepare(path, int(self.cfg["resolution"]))
            self.var_image.set(path)
            self.cfg["image_path"] = path
            
            d = os.path.dirname(path)
            b, ext = os.path.splitext(os.path.basename(path))
            
            if not self.var_corrected_image_path.get():
                self.var_corrected_image_path.set(os.path.join(d, f"{b}_corrigee{ext}"))
                
            if not self.var_stl_path.get():
                self.var_stl_path.set(os.path.join(d, f"{b}.stl"))
                
            save_config(self.cfg)
            self._set_status(f"Image chargée : {os.path.basename(path)}")
            self._do_preview()
                
        except Exception as e:
            messagebox.showerror("Erreur",
                                 f"Impossible de charger l'image :\n{e}")

    def _browse_corrected_image(self):
        p = filedialog.asksaveasfilename(
            title="Enregistrer l'image corrigée sous...",
            defaultextension=".jpg",
            filetypes=[("JPEG", "*.jpg"), ("PNG", "*.png")])
        if p:
            self.var_corrected_image_path.set(p)

    def _browse_stl(self):
        p = filedialog.asksaveasfilename(
            title="Enregistrer le STL sous...",
            defaultextension=".stl",
            filetypes=[("Fichier STL", "*.stl")])
        if p:
            self.var_stl_path.set(p)

    # ========================================================
    #  APERÇU
    # ========================================================
    def _schedule_preview(self):
        if self._preview_job:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(120, self._do_preview)

    def _do_preview(self):
        self._preview_job = None
        if self.img_base is None:
            return
        try:
            self.img_processed = apply_params(
                self.img_base,
                self.var_brightness.get(),
                self.var_contrast.get(),
                self.var_gamma.get(),
                self.var_blur.get())
            self._render_preview()
        except Exception as e:
            print(f"[APERÇU] {e}")

    def _render_preview(self):
        if self.img_processed is None:
            return
        w = self.preview_frame.winfo_width()
        h = self.preview_frame.winfo_height()
        if w < 50 or h < 50:
            w, h = 800, 800
            
        size = min(w, h) - 20
        if size < 50: size = 500
        
        img = self.img_processed.copy()
        img = img.resize((size, size), Image.LANCZOS)
        self.photo = ImageTk.PhotoImage(img)
        self.preview_label.configure(image=self.photo, text="")

    # ========================================================
    #  ENREGISTREMENT / CRÉATION
    # ========================================================
    def _save_and_create(self):
        if self.img_processed is None:
            messagebox.showwarning("Pas d'image", "Charge d'abord une image.")
            return

        try:
            self.cfg["diameter"]       = float(self.var_diameter.get())
            self.cfg["z_height"]       = float(self.var_z.get())
            self.cfg["base_epaisseur"] = float(self.var_base.get())
            self.cfg["brightness"]     = float(self.var_brightness.get())
            self.cfg["contrast"]       = float(self.var_contrast.get())
            self.cfg["gamma"]          = float(self.var_gamma.get())
            self.cfg["blur"]           = float(self.var_blur.get())
            self.cfg["corrected_image_path"] = self.var_corrected_image_path.get().strip()
            self.cfg["stl_path"]       = self.var_stl_path.get().strip()
            save_config(self.cfg)
        except ValueError:
            messagebox.showerror("Erreur", "Vérifie que les valeurs numériques sont correctes.")
            return

        corrected_path = self.var_corrected_image_path.get().strip()
        if not corrected_path:
            messagebox.showwarning("Erreur", "Veuillez indiquer où enregistrer l'image corrigée.")
            return
            
        try:
            self.img_processed.save(corrected_path, quality=95)
        except Exception as e:
            messagebox.showerror("Erreur Image", f"Impossible de sauvegarder l'image :\n{e}")
            return

        self._set_status("Image et configuration sauvegardées.")
        self._create_stl()

    def _create_stl(self):
        if not STL_OK:
            messagebox.showerror("numpy-stl manquant",
                                 "Installe-le avec :\n\npip install numpy-stl")
            return
        if self.img_base is None:
            messagebox.showwarning("Pas d'image", "Charge d'abord une image.")
            return
        try:
            diameter = float(self.var_diameter.get())
            z_height = float(self.var_z.get())
            base_ep  = float(self.var_base.get())
        except ValueError:
            messagebox.showerror("Erreur", "Vérifie les valeurs numériques.")
            return

        stl_path = self.var_stl_path.get().strip()
        if not stl_path:
            stl_path = filedialog.asksaveasfilename(
                title="Enregistrer le STL sous...",
                defaultextension=".stl",
                filetypes=[("Fichier STL", "*.stl")])
            if not stl_path:
                return
            self.var_stl_path.set(stl_path)
            self.cfg["stl_path"] = stl_path
            save_config(self.cfg)

        self._set_status("Génération du STL…")
        self.update_idletasks()

        img_final = apply_params(
            self.img_base,
            self.var_brightness.get(),
            self.var_contrast.get(),
            self.var_gamma.get(),
            self.var_blur.get())

        try:
            nb = generate_stl(img_final, stl_path,
                              diameter, base_ep, z_height)
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Erreur STL", str(e))
            self._set_status("")
            return

        self._stl_path = stl_path
        self._set_status(f"STL créé : {os.path.basename(stl_path)}")
        messagebox.showinfo("Succès",
                            f"✅ Image sauvegardée !\n✅ STL généré !\n\n{stl_path}\n({nb} triangles)")

        try:
            os.startfile(os.path.dirname(stl_path))
        except Exception:
            pass

    # ========================================================
    #  LOGICIEL EXTERNE
    # ========================================================
    def _choose_software(self):
        if sys.platform == "win32":
            ft = [("Exécutables", "*.exe"), ("Tous", "*.*")]
        else:
            ft = [("Tous", "*.*")]
        p = filedialog.askopenfilename(
            title="Choisis le logiciel STL (ex : DeskProto.exe, VCarve.exe…)",
            filetypes=ft)
        if p:
            self.cfg["external_software"] = p
            save_config(self.cfg)
            self._refresh_software_label()
            self._set_status(f"Logiciel enregistré : {os.path.basename(p)}")

    def _refresh_software_label(self):
        p = self.cfg.get("external_software", "").strip()
        if p and os.path.isfile(p):
            self.btn_software.configure(
                text=f"⚙  Logiciel STL : {os.path.basename(p)}")
            self.btn_open.configure(text=f"🚀  Ouvrir dans {os.path.basename(p)}")
        else:
            self.btn_software.configure(text="⚙  Configurer le logiciel STL")
            self.btn_open.configure(text="🚀  Ouvrir le STL")

    def _open_in_software(self):
        if not self._stl_path or not os.path.isfile(self._stl_path):
            p = self.var_stl_path.get().strip()
            if p and os.path.isfile(p):
                self._stl_path = p
            else:
                messagebox.showwarning("Pas de STL", "Crée d'abord un STL (bouton OK ou CRÉER LE STL).")
                return
                
        exe = self.cfg.get("external_software", "").strip()
        if not exe or not os.path.isfile(exe):
            if not messagebox.askyesno(
                    "Logiciel non configuré",
                    "Aucun logiciel n'est configuré.\n"
                    "Veux-tu en choisir un maintenant ?"):
                return
            self._choose_software()
            exe = self.cfg.get("external_software", "").strip()
            if not exe or not os.path.isfile(exe):
                return
        try:
            subprocess.Popen([exe, self._stl_path])
            self._set_status(f"Lancement de {os.path.basename(exe)}…")
        except Exception as e:
            messagebox.showerror("Erreur",
                                 f"Impossible de lancer le logiciel :\n{e}")

    # ========================================================
    def _set_status(self, txt):
        self.lbl_status.configure(text=txt)


# ============================================================
if __name__ == "__main__":
    App().mainloop()