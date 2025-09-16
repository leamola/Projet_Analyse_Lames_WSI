import tkinter as tk
from tkinter import messagebox, filedialog, Toplevel, ttk, simpledialog
import subprocess, sys, os, json, traceback, datetime, glob
from PIL import Image, ImageTk  # (si besoin plus tard)

# =========================
#  Environnement portable
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LIBVIPS_BIN    = os.path.join(BASE_DIR, "tools", "libvips", "bin")
OPENSLIDE_BIN  = os.path.join(BASE_DIR, "tools", "openslide", "bin")
MAGICK_CODERS  = os.path.join(LIBVIPS_BIN, "coders")  # si tu as copié les coders ImageMagick ici

# Ajoute les dossiers DLL en tête du PATH + search path Windows
for d in (LIBVIPS_BIN, OPENSLIDE_BIN):
    if os.path.isdir(d):
        try:
            os.add_dll_directory(d)  # Python 3.8+
        except Exception:
            pass
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")

# *** FORCER pyvips à utiliser NOTRE libvips (et pas le wheel) ***
os.environ["PYVIPS_USE_BINARY"]   = "0"
os.environ["PYVIPS_LIBRARY_PATH"] = LIBVIPS_BIN

# Si tu as déposé les coders ImageMagick (pour d'autres formats)
if os.path.isdir(MAGICK_CODERS):
    os.environ["MAGICK_HOME"] = LIBVIPS_BIN
    os.environ["MAGICK_CODER_MODULE_PATH"] = MAGICK_CODERS

# =========================
#  Logs
# =========================
ENABLE_LOGS = False
if ENABLE_LOGS:
    LOG_DIR = os.path.join(BASE_DIR, "logs")
    os.makedirs(LOG_DIR, exist_ok=True)
    LOG_FILE = os.path.join(LOG_DIR, "toolbox.log")

    def _excepthook(exc_type, exc, tb):
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n=== %s ===\n" % datetime.datetime.now().isoformat(timespec="seconds"))
            traceback.print_exception(exc_type, exc, tb, file=f)

    sys.excepthook = _excepthook

# =========================
#  Imports optionnels
# =========================
try:
    import boost_runtime
except Exception:
    boost_runtime = None

try:
    import pyvips   # via pyvips-binary si présent
    VIPS_OK = True
    # [NEW] log console utile pour vérifier la version chargée
    try:
        print("pyvips OK — libvips version:", pyvips.version(0))
    except Exception:
        pass
except Exception:
    pyvips = None
    VIPS_OK = False
    print("pyvips KO — non importé")

# =========================
#  Dossiers I/O
# =========================
base_output = os.path.join(BASE_DIR, "output")
EXTRACTED  = os.path.join(base_output, "extracted_lames")
ANNOTATED  = os.path.join(base_output, "annotated")
DETECTED   = os.path.join(base_output, "detected")
RESULTS    = os.path.join(base_output, "results")
for p in (EXTRACTED, ANNOTATED, DETECTED, RESULTS):
    os.makedirs(p, exist_ok=True)

# =========================
#  Thème & Layout
# =========================
COULEUR_FOND   = "#151829"
COULEUR_ACCENT = "#43b047"
COULEUR_TEXTE  = "white"
COULEUR_BTN    = "#23263a"
COULEUR_BTN_H  = "#2c3050"
COULEUR_BTN_P  = "#5fd06b"
COULEUR_BTN_S  = "#666879"

POLICE_TITRE   = ("Segoe UI", 18, "bold")
POLICE_BOUTON  = ("Segoe UI", 11)

CARD_W   = 560       # largeur “carte/bouton”
ROW_H    = 44
DOT_SIZE = 22

labels_etapes: dict[str, tk.Label] = {}
info_frames:   dict[str, tk.Frame] = {}
info_visible:  dict[str, bool]     = {}
_current_open_key: str | None      = None  # accordéon

# Empêche les relances et les clics pendant une étape longue
RUNNING = False
def _busy(on: bool):
    """Verrou global + curseur système."""
    global RUNNING
    RUNNING = bool(on)
    try:
        root.config(cursor="watch" if on else "")
        root.update_idletasks()
    except Exception:
        pass

# =========================
#  Helpers
# =========================
def open_folder(path: str):
    try:
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        messagebox.showwarning("Ouverture dossier", f"Impossible d'ouvrir :\n{path}\n\n{e}")

def open_file(path: str):
    try:
        if not os.path.exists(path):
            messagebox.showwarning("Fichier introuvable", f"Le fichier n'existe pas encore :\n{path}")
            return
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        messagebox.showwarning("Ouverture fichier", f"Impossible d'ouvrir :\n{path}\n\n{e}")

def safe_quit():
    if messagebox.askyesno("Quitter", "Fermer Pathology Toolbox ?"):
        try:
            root.destroy()
        except Exception:
            os._exit(0)

# =========================
#  Widgets custom
# =========================
class RoundedButton(tk.Canvas):
    def __init__(self, master, text, command=None, width=CARD_W, height=ROW_H, radius=18,
                 bg=COULEUR_BTN, fg=COULEUR_TEXTE, hover_bg=COULEUR_BTN_H,
                 active_bg=COULEUR_ACCENT, font=POLICE_BOUTON, **kw):
        super().__init__(master, width=width, height=height, bg=COULEUR_FOND, highlightthickness=0, **kw)
        self.command = command
        self._W, self._H, self._R = width, height, radius
        self._bg, self._fg = bg, fg
        self._hover_bg, self._active_bg = hover_bg, active_bg
        self._txt = text
        self._font = font
        self._is_pressed = False
        self._draw(self._bg)
        self.bind("<Enter>",  lambda e: self._redraw(self._hover_bg))
        self.bind("<Leave>",  lambda e: self._redraw(self._bg if not self._is_pressed else self._active_bg))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.configure(cursor="hand2")

    def _rounded_rect(self, x1, y1, x2, y2, r, **opts):
        self.create_arc(x1, y1, x1+2*r, y1+2*r, start=90, extent=90, style="pieslice", **opts)
        self.create_arc(x2-2*r, y1, x2, y1+2*r, start=0, extent=90, style="pieslice", **opts)
        self.create_arc(x2-2*r, y2-2*r, x2, y2, start=270, extent=90, style="pieslice", **opts)
        self.create_arc(x1, y2-2*r, x1+2*r, y2, start=180, extent=90, style="pieslice", **opts)
        self.create_rectangle(x1+r, y1, x2-r, y2, **opts)
        self.create_rectangle(x1, y1+r, x2, y2-r, **opts)

    def _draw(self, fill):
        self.delete("all")
        self._rounded_rect(2, 2, self._W-2, self._H-2, self._R, fill=fill, outline=fill)
        self.create_text(self._W//2, self._H//2, text=self._txt, fill=self._fg, font=self._font)

    def _redraw(self, fill):
        if not self._is_pressed:
            self._draw(fill)

    def _press(self, _):
        self._is_pressed = True
        self._draw(self._active_bg)

    def _release(self, _):
        if self._is_pressed:
            self._is_pressed = False
            self._draw(self._hover_bg)
            if callable(self.command):
                self.after(10, self.command)

class InfoDot(tk.Canvas):
    def __init__(self, master, step_key, on_toggle, size=DOT_SIZE):
        super().__init__(master, width=size, height=size, bg=COULEUR_FOND, highlightthickness=0)
        self.step_key = step_key
        self.on_toggle = on_toggle
        self.size = size
        self._draw(COULEUR_BTN_H)
        self.bind("<Enter>", lambda e: self._draw("#4a4a6b"))
        self.bind("<Leave>", lambda e: self._draw(COULEUR_BTN_H))
        self.bind("<Button-1>", lambda e: self.on_toggle(self.step_key))
        self.configure(cursor="hand2")

    def _draw(self, fill):
        self.delete("all")
        r = self.size // 2
        self.create_oval(2, 2, self.size - 2, self.size - 2, fill=fill, outline=fill)
        self.create_text(r, r, text="i", fill="white", font=("Segoe UI", 11, "bold"))

# =========================
#  Progress & statuts
# =========================
def reset_step_label(step_key, text=""):
    if step_key in labels_etapes:
        labels_etapes[step_key].config(text=text, fg=COULEUR_TEXTE)
        try:
            root.update_idletasks(); root.update()
        except Exception:
            pass

def set_step_ok(step_key, msg):
    if step_key in labels_etapes:
        labels_etapes[step_key].config(text=f"✔ {msg} ✅", fg="#7CFC00")
        try:
            root.update_idletasks(); root.update()
        except Exception:
            pass

def set_step_cancel(step_key, msg="⛔ Opération annulée"):
    if step_key in labels_etapes:
        labels_etapes[step_key].config(text=f"⛔ {msg}", fg="#ffb3b3")
        try:
            root.update_idletasks(); root.update()
        except Exception:
            pass

def afficher_progression(valeur, total, _label_widget=None):
    try:
        total = max(int(total), 1)
        percent = int(max(0, min(100, (valeur / total) * 100)))
    except Exception:
        percent = 0
    progress_bar["value"] = percent
    progress_pct.config(text=f"{percent}%")
    try:
        root.update_idletasks(); root.update()
    except Exception:
        pass

def spinner_on():
    try:
        progress_bar.stop()
        progress_bar.config(mode="indeterminate", maximum=100, value=0)
        progress_bar.start(12)
        progress_pct.config(text="…")
        root.update_idletasks()
    except Exception:
        pass

def spinner_off():
    try:
        progress_bar.stop()
        progress_bar.config(mode="determinate")
        root.update_idletasks()
    except Exception:
        pass

# --------- Résultats (nom avec %) ----------
def _format_pct_for_name(seuil):
    if float(seuil).is_integer():
        return f"{int(seuil)}p"
    return f"{seuil:.2f}".rstrip("0").rstrip(".") + "p"

def rename_analysis_csv_with_threshold(seuil):
    src = os.path.join(RESULTS, "analyse_CD7.csv")
    if os.path.exists(src):
        dst = os.path.join(RESULTS, f"analyse_CD7_seuil_{_format_pct_for_name(seuil)}.csv")
        try:
            if os.path.exists(dst):
                os.remove(dst)
            os.replace(src, dst)
            return dst
        except Exception:
            return src
    files = glob.glob(os.path.join(RESULTS, "analyse_CD7*.csv"))
    return max(files, key=os.path.getmtime) if files else None

def get_latest_analysis_csv():
    files = glob.glob(os.path.join(RESULTS, "analyse_CD7*.csv"))
    return max(files, key=os.path.getmtime) if files else None

def open_latest_results_csv():
    p = get_latest_analysis_csv()
    if p:
        open_file(p)
    else:
        messagebox.showwarning("CSV introuvable", "Aucun CSV d’analyse trouvé.\nLance d'abord l’analyse des résultats.")

def get_resume_detection_csv():
    p = os.path.join(DETECTED, "resume_detection.csv")
    return p if os.path.exists(p) else None

def open_resume_detection_csv():
    p = get_resume_detection_csv()
    if p:
        open_file(p)
    else:
        messagebox.showwarning("Fichier introuvable", "resume_detection.csv introuvable.\nLance d'abord la détection.")

# =========================
#  Etapes (imports paresseux)
# =========================
def _ask_threshold(current=None):
    try:
        iv = None if current is None else float(current)
    except Exception:
        iv = None
    val = simpledialog.askfloat(
        "Seuil CD7 (%)",
        "Quel est le seuil (en %) à partir duquel on parle de perte d'expression CD7 ?",
        parent=root, minvalue=0.0, maxvalue=100.0, initialvalue=iv
    )
    return val  # None si Annuler

def preprocessing_gui():
    from preprocessing import extract_files_from_zip, detect_markers
    zip_path = filedialog.askopenfilename(title="Sélectionnez un fichier ZIP", filetypes=[("Fichiers ZIP", "*.zip")])
    if not zip_path:
        set_step_cancel("preprocessing", "Extraction annulée")
        return
    try:
        marker_options = detect_markers(zip_path)
    except Exception as e:
        messagebox.showerror("Erreur", f"Impossible d'ouvrir l'archive ZIP.\n{e}")
        return
    if not marker_options:
        messagebox.showwarning("Aucun marqueur", "Aucun marqueur détecté dans l'archive.")
        return

    def valider_selection():
        selected = [m for m, var in checkbox_vars.items() if var.get() == 1]
        if not selected:
            messagebox.showwarning("Attention", "Aucun marqueur sélectionné.")
            return
        fen.destroy()
        try:
            _busy(True)
            spinner_on()
            try:
                def update_progress(c, t): afficher_progression(c, t)
                extract_files_from_zip(zip_path, selected, EXTRACTED, progress_callback=update_progress)
            finally:
                spinner_off()
            set_step_ok("preprocessing", "Extraction des fichiers terminée")
        except Exception as e:
            labels_etapes["preprocessing"].config(text="❌ Échec de l'extraction", fg="red")
            messagebox.showerror("Erreur d'extraction", str(e))
        finally:
            _busy(False)

    fen = Toplevel(root)
    fen.title("Sélection des marqueurs")
    fen.configure(bg=COULEUR_FOND)
    fen.geometry("420x340")
    tk.Label(fen, text="🧪 Choisissez les marqueurs à traiter :", bg=COULEUR_FOND,
             fg=COULEUR_TEXTE, font=POLICE_BOUTON).pack(pady=10)
    checkbox_vars = {}
    for m in marker_options:
        var = tk.IntVar(value=1)
        tk.Checkbutton(fen, text=m, variable=var, bg=COULEUR_FOND, fg=COULEUR_TEXTE,
                       selectcolor=COULEUR_ACCENT, activebackground=COULEUR_FOND,
                       font=POLICE_BOUTON).pack(anchor="w", padx=30)
        checkbox_vars[m] = var
    RoundedButton(fen, text="Valider", command=valider_selection,
                  width=220, height=40, radius=14, bg=COULEUR_ACCENT,
                  hover_bg="#5bcf61", active_bg="#43a047").pack(pady=16)

def detect_slide_mask_gui():
    global RUNNING
    if RUNNING:
        return
    try:
        from annotation_global import lancer_annotation_gui
        status_label = labels_etapes.get("annotation_global")
        if status_label:
            status_label.config(text="🖍️ Annotation globale en cours...", fg=COULEUR_TEXTE)
            root.update_idletasks()

        # ⛔ pas de spinner ici ; on passe en déterminé
        try:
            progress_bar.stop()
        except Exception:
            pass
        progress_bar.config(mode="determinate", maximum=100, value=0)
        progress_pct.config(text="0%")
        root.update_idletasks()

        _busy(True)
        # ✅ passer les bons widgets (l’annotation gère la progression + label et met “terminée” elle-même)
        lancer_annotation_gui(root, progress_bar, progress_pct, status_label)
        # (ne pas appeler set_step_ok pour éviter les doublons)
    except Exception as e:
        if "annotation_global" in labels_etapes:
            labels_etapes["annotation_global"].config(text="❌ Erreur annotation", fg="red")
        messagebox.showerror("Erreur annotation", str(e))
    finally:
        _busy(False)

def lancer_script(script_name):
    global RUNNING
    if RUNNING:
        return  # ignore pendant un traitement
    step_key = script_name.split(".")[0]
    reset_step_label(step_key)

    if script_name == "preprocessing.py":
        preprocessing_gui()

    elif script_name == "annotation_global.py":
        detect_slide_mask_gui()

    elif script_name == "cell_detection.py":
        from cell_detection import detecter_noyaux_dab
        s = _ask_threshold()
        if s is None:
            set_step_cancel("cell_detection", "Détection annulée (seuil non défini)")
            return
        try:
            with open(os.path.join(DETECTED, "params.json"), "w", encoding="utf-8") as f:
                json.dump({"seuil_cd7_percent": float(s)}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        try:
            _busy(True)
            spinner_on()
            try:
                # ✅ passer progress_pct
                detecter_noyaux_dab(root, progress_bar, progress_pct)
            finally:
                spinner_off()
            set_step_ok("cell_detection", "Détection DAB terminée")
        except Exception as e:
            labels_etapes["cell_detection"].config(text="❌ Erreur détection", fg="red")
            messagebox.showerror("Erreur détection", str(e))
        finally:
            _busy(False)

    elif script_name == "result.py":
        from result import analyser_resultats_cd7
        params = os.path.join(DETECTED, "params.json")
        seuil = None
        if os.path.exists(params):
            try:
                seuil = float(json.load(open(params, "r", encoding="utf-8")).get("seuil_cd7_percent"))
            except Exception:
                pass
        new_s = _ask_threshold(seuil)
        if new_s is None:
            set_step_cancel("result", "Analyse annulée (seuil non défini)")
            return
        try:
            with open(params, "w", encoding="utf-8") as f:
                json.dump({"seuil_cd7_percent": float(new_s)}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        try:
            _busy(True)
            spinner_on()
            try:
                # ✅ passer progress_pct
                analyser_resultats_cd7(root, progress_bar, progress_pct, seuil_ratio_cd7=float(new_s))
            finally:
                spinner_off()
            rename_analysis_csv_with_threshold(float(new_s))
            set_step_ok("result", "Analyse CD7 terminée")
        except Exception as e:
            labels_etapes["result"].config(text="❌ Erreur analyse", fg="red")
            messagebox.showerror("Erreur analyse", str(e))
        finally:
            _busy(False)

# =========================
#  Pipeline “tout”
# =========================
def lancer_tout_pipeline():
    from preprocessing import extract_files_from_zip, detect_markers
    from annotation_global import lancer_annotation_gui
    from cell_detection import detecter_noyaux_dab
    from result import analyser_resultats_cd7

    global RUNNING
    if RUNNING:
        return
    _busy(True)
    try:
        for k in labels_etapes:
            reset_step_label(k)

        # 1) Extraction
        zip_path = filedialog.askopenfilename(title="Sélectionnez un fichier ZIP", filetypes=[("Fichiers ZIP", "*.zip")])
        if not zip_path:
            set_step_cancel("preprocessing", "Extraction annulée")
            return
        try:
            options = detect_markers(zip_path)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'ouvrir l'archive ZIP.\n{e}")
            return
        if not options:
            messagebox.showwarning("Aucun marqueur", "Aucun marqueur détecté dans l'archive.")
            set_step_cancel("preprocessing", "Aucun marqueur")
            return

        selected = []
        def valider_selection_local():
            sel = [m for m, var in checkbox_vars.items() if var.get() == 1]
            if not sel:
                messagebox.showwarning("Attention", "Aucun marqueur sélectionné.", parent=fen)
                return
            selected.extend(sel); fen.destroy()

        fen = Toplevel(root); fen.title("Sélection des marqueurs"); fen.configure(bg=COULEUR_FOND); fen.geometry("420x340")
        tk.Label(fen, text="🧪 Choisissez les marqueurs à traiter :", bg=COULEUR_FOND, fg=COULEUR_TEXTE,
                 font=POLICE_BOUTON).pack(pady=10)
        checkbox_vars = {}
        for m in options:
            var = tk.IntVar(value=1)
            tk.Checkbutton(fen, text=m, variable=var, bg=COULEUR_FOND, fg=COULEUR_TEXTE,
                           selectcolor=COULEUR_ACCENT, activebackground=COULEUR_FOND,
                           font=POLICE_BOUTON).pack(anchor="w", padx=30)
            checkbox_vars[m] = var
        RoundedButton(fen, text="Valider", command=valider_selection_local, width=220, height=40, radius=14,
                      bg=COULEUR_ACCENT, hover_bg="#5bcf61", active_bg="#43a047").pack(pady=16)
        fen.grab_set(); root.wait_window(fen)
        if not selected:
            set_step_cancel("preprocessing", "Extraction annulée")
            return

        try:
            spinner_on()
            try:
                def update_progress(c, t): afficher_progression(c, t)
                extract_files_from_zip(zip_path, selected, EXTRACTED, progress_callback=update_progress)
            finally:
                spinner_off()
            set_step_ok("preprocessing", "Extraction des fichiers terminée")
        except Exception as e:
            labels_etapes["preprocessing"].config(text="❌ Échec de l'extraction", fg="red")
            messagebox.showerror("Erreur d'extraction", str(e))
            return

        # 2) Annotation — pas de spinner, barre déterminée
        try:
            progress_bar.stop()
        except Exception:
            pass
        progress_bar.config(mode="determinate", maximum=100, value=0)
        progress_pct.config(text="0%")
        root.update_idletasks()

        lancer_annotation_gui(root, progress_bar, progress_pct, labels_etapes["annotation_global"])
        # (ne pas appeler set_step_ok ici, c'est déjà fait par l’annotation via le label)

        # 3) Détection
        s = _ask_threshold()
        if s is None:
            set_step_cancel("cell_detection", "Détection annulée (seuil non défini)")
            return
        try:
            with open(os.path.join(DETECTED, "params.json"), "w", encoding="utf-8") as f:
                json.dump({"seuil_cd7_percent": float(s)}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        try:
            spinner_on()
            try:
                # ✅ passer progress_pct
                detecter_noyaux_dab(root, progress_bar, progress_pct)
            finally:
                spinner_off()
            set_step_ok("cell_detection", "Détection DAB terminée")
        except Exception as e:
            labels_etapes["cell_detection"].config(text="❌ Erreur détection", fg="red")
            messagebox.showerror("Erreur détection", str(e))
            return

        # 4) Analyse
        new_s = _ask_threshold(float(s))
        if new_s is None:
            set_step_cancel("result", "Analyse annulée (seuil non défini)")
            return
        try:
            with open(os.path.join(DETECTED, "params.json"), "w", encoding="utf-8") as f:
                json.dump({"seuil_cd7_percent": float(new_s)}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        try:
            spinner_on()
            try:
                # ✅ passer progress_pct
                analyser_resultats_cd7(root, progress_bar, progress_pct, seuil_ratio_cd7=float(new_s))
            finally:
                spinner_off()
            rename_analysis_csv_with_threshold(float(new_s))
            set_step_ok("result", "Analyse CD7 terminée")
        except Exception as e:
            labels_etapes["result"].config(text="❌ Erreur analyse", fg="red")
            messagebox.showerror("Erreur analyse", str(e))
            return

        messagebox.showinfo("Pipeline terminé", "✅ Toutes les étapes sont terminées.")
    finally:
        _busy(False)

# =========================
#  Toggle panneau “i” (accordéon)
# =========================
def toggle_info(step_key):
    if RUNNING:
        return  # ignore pendant une étape en cours
    global _current_open_key
    fr = info_frames.get(step_key)
    if not fr:
        return
    if _current_open_key and _current_open_key in info_frames and _current_open_key != step_key:
        info_frames[_current_open_key].forget()
        info_visible[_current_open_key] = False
    if info_visible.get(step_key, False):
        fr.forget()
        info_visible[step_key] = False
        _current_open_key = None
    else:
        fr.pack(after=labels_etapes[step_key], anchor="center", pady=(4, 10), fill="x")
        info_visible[step_key] = True
        _current_open_key = step_key

# =========================
#  Fenêtre
# =========================
root = tk.Tk()
root.title("🧬 PathologyToolbox")
root.configure(bg=COULEUR_FOND)
root.geometry("700x880")
root.minsize(700, 740)
root.protocol("WM_DELETE_WINDOW", safe_quit)

# Barre de progression en haut
style = ttk.Style()
try:
    style.theme_use("clam")
except Exception:
    pass
style.configure("Green.Horizontal.TProgressbar",
                troughcolor=COULEUR_FOND, background=COULEUR_ACCENT,
                thickness=14, bordercolor=COULEUR_FOND,
                lightcolor=COULEUR_ACCENT, darkcolor=COULEUR_ACCENT)

topbar = tk.Frame(root, bg=COULEUR_FOND)
topbar.pack(side="top", fill="x")
progress_bar = ttk.Progressbar(topbar, orient="horizontal", mode="determinate",
                               style="Green.Horizontal.TProgressbar", length=100)
progress_bar.pack(fill="x")
progress_pct = tk.Label(topbar, text="0%", bg=COULEUR_FOND, fg="white", font=("Segoe UI", 9))
progress_pct.place(relx=1.0, x=-10, y=0, anchor="ne")

# Contenu scrollable
outer = tk.Frame(root, bg=COULEUR_FOND)
outer.pack(fill="both", expand=True)

canvas = tk.Canvas(outer, bg=COULEUR_FOND, highlightthickness=0)
vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
canvas.configure(yscrollcommand=vsb.set)
canvas.pack(side="left", fill="both", expand=True)
vsb.pack(side="right", fill="y")

content = tk.Frame(canvas, bg=COULEUR_FOND)
content_id = canvas.create_window((0, 0), window=content, anchor="n")

def _on_frame_configure(_):
    canvas.configure(scrollregion=canvas.bbox("all"))
content.bind("<Configure>", _on_frame_configure)

def _on_canvas_configure(e):
    canvas.itemconfigure(content_id, width=e.width)
canvas.bind("<Configure>", _on_canvas_configure)

def _on_mousewheel(event):
    delta = int(-1*(event.delta/120)) if event.delta else 0
    if delta:
        canvas.yview_scroll(delta, "units")
root.bind_all("<MouseWheel>", _on_mousewheel)
root.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-3, "units"))  # Linux
root.bind_all("<Button-5>", lambda e: canvas.yview_scroll( 3, "units"))

# Titres centrés
tk.Label(content, text="Pathology Toolbox", font=POLICE_TITRE,
         bg=COULEUR_FOND, fg=COULEUR_ACCENT).pack(pady=(16, 0))
tk.Label(content, text="Interface de traitement histologique",
         font=("Segoe UI", 10), bg=COULEUR_FOND, fg=COULEUR_TEXTE).pack(pady=(2, 18))

# Étapes
steps_container = tk.Frame(content, bg=COULEUR_FOND)
steps_container.pack(fill="x")

scripts = {
    "1 - Extraction des fichiers": "preprocessing.py",
    "2 - Annotation globale":      "annotation_global.py",
    "3 - Détection des cellules DAB": "cell_detection.py",
    "4 - Analyse des résultats":   "result.py"
}

descriptions = {
    "preprocessing": (
        "Sélectionne un fichier ZIP (brut du scanner ou export QuPath). "
        "L’archive peut contenir un ou plusieurs patients. Les marqueurs sont détectés, "
        "les lames extraites et les noms standardisés si nécessaire."
    ),
    "annotation_global": (
        "Génère un masque (contour tissu) pour chaque lame et exporte un JSON par lame "
        "à partir duquel la détection s’exécute."
    ),
    "cell_detection": (
        "Détecte les noyaux DAB dans les zones annotées, produit des PNG annotés "
        "et un résumé CSV des comptages."
    ),
    "result": (
        "Agrège par patient et calcule la proportion PERTE/RÉFÉRENCE (%) (ex. CD7 vs CD3). "
        "Utilise le seuil saisi. Génère un CSV d’analyse et le renomme avec le %."
    ),
}

# Construction centrée + pastille “i”
for label_text, script_file in scripts.items():
    row = tk.Frame(steps_container, bg=COULEUR_FOND)
    row.pack(anchor="center", pady=(8, 4))

    card = tk.Frame(row, bg=COULEUR_FOND, width=CARD_W, height=ROW_H)
    card.pack_propagate(False)
    card.pack()

    btn = RoundedButton(
        card, text=label_text, command=lambda s=script_file: lancer_script(s),
        width=CARD_W, height=ROW_H, radius=18,
        bg=COULEUR_BTN, hover_bg=COULEUR_BTN_H, active_bg=COULEUR_BTN_P
    )
    btn.pack(fill="both", expand=True)

    step_key = script_file.split(".")[0]
    dot = InfoDot(card, step_key, on_toggle=toggle_info, size=DOT_SIZE)
    dot.place(relx=1.0, rely=0.5, x=-10, anchor="e")  # collé au bord droit

    # Statut sous le bouton
    st = tk.Label(steps_container, text="", bg=COULEUR_FOND, fg=COULEUR_TEXTE,
                  font=("Segoe UI", 10), anchor="w", justify="left", wraplength=CARD_W)
    st.pack(anchor="center")
    labels_etapes[step_key] = st

    # --- Panneau “i” (description + 2 boutons max) ---
    fr = tk.Frame(steps_container, bg=COULEUR_FOND, highlightthickness=0)
    info_frames[step_key] = fr
    info_visible[step_key] = False

    tk.Label(fr, text=descriptions.get(step_key, ""), bg=COULEUR_FOND, fg=COULEUR_TEXTE,
             font=("Segoe UI", 10), anchor="center", justify="left", wraplength=CARD_W).pack(
        fill="x", padx=0, pady=(4, 6)
    )

    actions = tk.Frame(fr, bg=COULEUR_FOND, width=CARD_W)
    actions.pack_propagate(False)
    actions.pack(anchor="center")
    # grille centrée à 2 colonnes
    for c in range(2):
        actions.grid_columnconfigure(c, weight=1)

    def add_half(row, col, text, cmd):
        RoundedButton(actions, text=text, command=cmd, width=int(CARD_W/2)-8, height=36, radius=14,
                      bg=COULEUR_BTN_S, hover_bg="#6b6b6b", active_bg="#7a7a7a").grid(
            row=row, column=col, sticky="ew", padx=5, pady=5
        )

    if step_key == "preprocessing":
        RoundedButton(actions, text="📂 Ouvrir ‘extracted_lames’",
                      command=lambda: open_folder(EXTRACTED),
                      width=CARD_W, height=36, radius=14,
                      bg=COULEUR_BTN_S, hover_bg="#6b6b6b", active_bg="#7a7a7a").grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=5
        )

    elif step_key == "annotation_global":
        RoundedButton(actions, text="📂 Ouvrir ‘annotated’ (JSON)",
                      command=lambda: open_folder(ANNOTATED),
                      width=CARD_W, height=36, radius=14,
                      bg=COULEUR_BTN_S, hover_bg="#6b6b6b", active_bg="#7a7a7a").grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=5
        )

    elif step_key == "cell_detection":
        add_half(0, 0, "📂 Ouvrir ‘detected’", lambda: open_folder(DETECTED))
        add_half(0, 1, "📄 Ouvrir resume_detection.csv", open_resume_detection_csv)

    elif step_key == "result":
        add_half(0, 0, "📂 Ouvrir ‘results’", lambda: open_folder(RESULTS))
        add_half(0, 1, "📄 Ouvrir analyse (dernier)", open_latest_results_csv)

# Bas de page (centré)
RoundedButton(content, text="📄 Ouvrir CSV résultats (analyse prioritaire)",
              command=open_latest_results_csv, width=CARD_W, height=42, radius=18,
              bg=COULEUR_BTN_S, hover_bg="#6b6b6b", active_bg="#7a7a7a").pack(pady=(20, 0), anchor="center")

RoundedButton(content, text="🚀 Lancer tout le pipeline",
              command=lancer_tout_pipeline, width=CARD_W, height=46, radius=20,
              bg=COULEUR_ACCENT, hover_bg="#5bcf61", active_bg="#43a047").pack(pady=18, anchor="center")

RoundedButton(content, text="Quitter", command=safe_quit,
              width=int(CARD_W/2), height=40, radius=16,
              bg="#9b3b3b", hover_bg="#b14a4a", active_bg="#c62828").pack(pady=(0, 22), anchor="center")

root.mainloop()
