# annotation_global.py — preview persistant & ultra-léger (DICOM/NDPI/SVS/TIFF)
import os, json, time, subprocess, tempfile
import numpy as np
import cv2, tifffile
from tkinter import Toplevel, Label, Button, Radiobutton, StringVar, messagebox
from PIL import Image, ImageTk

# ===== Réglages “light” =====
PREVIEW_MAX_PIX = 2_000_000   # ~2 MP
THUMB_MAX_DIM   = 2200        # largeur max vignette

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIPS_EXE = os.path.join(BASE_DIR, "tools", "libvips", "bin", "vips.exe")

# ===== Imports optionnels =====
try:
    import openslide
except Exception:
    openslide = None

try:
    import pydicom
except Exception:
    pydicom = None

try:
    import pyvips
    VIPS_OK = True
except Exception:
    pyvips = None
    VIPS_OK = False


# ---------- Helpers ----------
def _ensure_rgb_u8(arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 2:
        arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
    elif arr.ndim == 3:
        if arr.shape[2] == 4:
            arr = arr[:, :, :3]
        elif arr.shape[2] == 1:
            arr = cv2.cvtColor(arr[:, :, 0], cv2.COLOR_GRAY2RGB)
    if arr.dtype != np.uint8:
        mn, mx = float(arr.min()), float(arr.max())
        if mx > mn:
            arr = ((arr - mn) * (255.0 / (mx - mn))).astype(np.uint8)
        else:
            arr = np.zeros_like(arr, dtype=np.uint8)
    return arr

def _downscale_by_pixels(img: np.ndarray, max_pixels: int) -> np.ndarray:
    h, w = img.shape[:2]
    if h * w <= max_pixels:
        return img
    scale = (max_pixels / (h * w)) ** 0.5
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

def _adaptive_params(h: int, w: int):
    s = min(h, w)
    block = int(max(41, s / 40)) | 1   # impair
    ksize = max(11, int(s / 150))
    return block, ksize

def _openslide_preview(path: str, max_pixels: int = PREVIEW_MAX_PIX, max_dim: int = THUMB_MAX_DIM) -> np.ndarray:
    if openslide is None:
        raise RuntimeError("OpenSlide indisponible.")
    slide = openslide.OpenSlide(path)
    try:
        w0, h0 = slide.dimensions
        scale = 1.0
        if w0 * h0 > max_pixels:
            scale = (max_pixels / (w0 * h0)) ** 0.5
        tw = min(int(w0 * scale), max_dim)
        th = max(1, int(h0 * (tw / w0)))
        pil = slide.get_thumbnail((max(1, tw), max(1, th))).convert("RGB")
        arr = np.array(pil)
        return _ensure_rgb_u8(arr)
    finally:
        slide.close()

def _vips_cli_thumbnail(path: str, max_dim: int = THUMB_MAX_DIM) -> np.ndarray | None:
    """Fallback via vips.exe (utilise openslideload du CLI)."""
    if not os.path.exists(VIPS_EXE):
        return None
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "thumb.jpg")
        cmd = [VIPS_EXE, "thumbnail", path, out, str(max_dim)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if r.returncode != 0 or not os.path.exists(out):
                return None
            bgr = cv2.imread(out, cv2.IMREAD_COLOR)
            if bgr is None:
                return None
            return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        except Exception:
            return None


# ---------- Lecture d’un aperçu RGB sécurisé ----------
def _read_slide_rgb(image_path: str) -> np.ndarray:
    ext = os.path.splitext(image_path)[1].lower()

    # NDPI / SVS → OpenSlide thumbnail
    if ext in (".ndpi", ".svs"):
        return _openslide_preview(image_path)

    # TIFF
    if ext in (".tif", ".tiff"):
        img = tifffile.imread(image_path)
        if img.ndim == 3 and img.shape[0] in (3, 4) and (img.shape[2] not in (3, 4)):
            img = np.transpose(img, (1, 2, 0))
        return _downscale_by_pixels(_ensure_rgb_u8(img), PREVIEW_MAX_PIX)

    # DICOM : pyvips → OpenSlide → vips.exe → pydicom(1 frame)
    if ext == ".dcm":
        if VIPS_OK:
            # pyvips thumbnail
            try:
                thumb = pyvips.Image.thumbnail(image_path, THUMB_MAX_DIM)
                if thumb.bands == 1:
                    thumb = thumb.colourspace("srgb")
                elif thumb.bands >= 3:
                    thumb = thumb.extract_band(0, n=3)
                mem = thumb.write_to_memory()
                arr = np.frombuffer(mem, dtype=np.uint8).reshape(thumb.height, thumb.width, thumb.bands)
                return _ensure_rgb_u8(arr)
            except Exception:
                pass
            # pyvips new_from_file + resize streamé
            try:
                im = pyvips.Image.new_from_file(image_path, access="sequential")
                scale = THUMB_MAX_DIM / max(1, im.width)
                if scale < 1.0:
                    im = im.resize(scale)
                if im.bands == 1:
                    im = im.colourspace("srgb")
                elif im.bands >= 3:
                    im = im.extract_band(0, n=3)
                mem = im.write_to_memory()
                arr = np.frombuffer(mem, dtype=np.uint8).reshape(im.height, im.width, im.bands)
                return _ensure_rgb_u8(arr)
            except Exception:
                pass

        # OpenSlide direct
        try:
            return _openslide_preview(image_path)
        except Exception:
            pass

        # vips.exe CLI
        cli = _vips_cli_thumbnail(image_path)
        if cli is not None:
            return cli

        # pydicom en dernier recours (mono-frame seulement)
        if pydicom is None:
            raise RuntimeError("DICOM détecté mais pyvips/OpenSlide/vips.exe indisponibles.")
        ds = pydicom.dcmread(image_path, stop_before_pixels=True)
        n_frames = int(ds.get("NumberOfFrames", 1))
        if n_frames > 1:
            raise MemoryError(
                f"DICOM multi-frame détecté ({n_frames} frames). "
                f"Impossible d’obtenir une vignette sûre. Vérifie que pyvips utilise ton libvips local "
                f"(PYVIPS_USE_BINARY=0) ou utilise vips.exe/convertis en TIFF/NDPI."
            )
        ds = pydicom.dcmread(image_path)
        arr = ds.pixel_array
        photometric = str(getattr(ds, "PhotometricInterpretation", "")).upper()
        if photometric == "MONOCHROME1":
            arr = arr.max() - arr
        if arr.ndim == 3 and arr.shape[2] == 3 and photometric.startswith("YBR"):
            try:
                ycrcb = arr[..., [0, 2, 1]]
                arr = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2RGB)
            except Exception:
                pass
        return _downscale_by_pixels(_ensure_rgb_u8(arr), PREVIEW_MAX_PIX)

    # PNG/JPG…
    bgr = cv2.imread(image_path, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_ANYCOLOR)
    if bgr is None:
        raise RuntimeError(f"Format non supporté ou fichier illisible : {image_path}")
    if bgr.ndim == 2:
        img = cv2.cvtColor(bgr, cv2.COLOR_GRAY2RGB)
    else:
        img = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return _downscale_by_pixels(_ensure_rgb_u8(img), PREVIEW_MAX_PIX)


# ---------- Détection + JSON (et preview) ----------
def detect_slide_mask(image_path: str, output_json_path: str,
                      min_area: int = 20_000, area_ratio_thresh: float = 0.4):
    img = _read_slide_rgb(image_path)

    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    block, ksize = _adaptive_params(*gray.shape)
    blurred = cv2.GaussianBlur(gray, (ksize | 1, ksize | 1), 0)

    mask = cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,
        blockSize=block, C=2
    )
    kernel = np.ones((ksize, ksize), np.uint8)
    mask_clean = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2, ensure_ascii=False)
        overlay = img.copy()
        return 0, img, mask_clean, overlay

    areas    = [cv2.contourArea(c) for c in contours]
    max_area = max(areas) if areas else 0

    big = [c for c in contours
           if cv2.contourArea(c) >= min_area and (max_area == 0 or cv2.contourArea(c) >= area_ratio_thresh * max_area)]

    overlay = img.copy()
    cv2.drawContours(overlay, big, -1, (255, 0, 0), 4)

    out = []
    for i, c in enumerate(big):
        poly = c.squeeze().tolist()
        if not poly or isinstance(poly[0], (int, float)) or len(poly) < 3:
            continue
        out.append({
            "name": f"Slide_Area_{i+1}",
            "geometry": {"type": "Polygon", "coordinates": [poly]}
        })

    os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    return len(big), img, mask_clean, overlay


# ---------- Fenêtre de preview persistante ----------
def _show_preview_window(root, title, img_rgb, mask_bin, overlay_rgb, save_path_png=None):
    win = Toplevel(root); win.title(f"Prévisualisation — {title}")
    win.geometry("980x800"); win.configure(bg="#151829")
    mode = StringVar(value="overlay")
    lbl = Label(win, bg="#151829"); lbl.pack(fill="both", expand=True, padx=10, pady=10)

    def to_photo(arr):
        im = Image.fromarray(arr)
        maxw = max(400, win.winfo_width() - 40)
        maxh = max(300, win.winfo_height() - 140)
        im.thumbnail((maxw, maxh), Image.LANCZOS)
        return ImageTk.PhotoImage(im)

    mask_rgb = cv2.cvtColor(mask_bin, cv2.COLOR_GRAY2RGB)
    current = {"p": None}
    def refresh():
        m = mode.get()
        arr = overlay_rgb if m == "overlay" else (mask_rgb if m == "masque" else img_rgb)
        p = to_photo(arr); current["p"] = p; lbl.config(image=p)

    def save_png():
        if not save_path_png: return
        try:
            Image.fromarray(overlay_rgb).save(save_path_png)
            messagebox.showinfo("Enregistré", f"Preview sauvegardée :\n{save_path_png}", parent=win)
        except Exception as e:
            messagebox.showwarning("Erreur", f"Impossible d’enregistrer :\n{e}", parent=win)

    ctr = Toplevel(win); ctr.title("Affichage"); ctr.geometry("360x120+40+40"); ctr.configure(bg="#151829")
    Radiobutton(ctr, text="Image",   variable=mode, value="image",   command=refresh, bg="#151829", fg="white", selectcolor="#43b047").pack(side="left", padx=8, pady=8)
    Radiobutton(ctr, text="Masque",  variable=mode, value="masque",  command=refresh, bg="#151829", fg="white", selectcolor="#43b047").pack(side="left", padx=8, pady=8)
    Radiobutton(ctr, text="Overlay", variable=mode, value="overlay", command=refresh, bg="#151829", fg="white", selectcolor="#43b047").pack(side="left", padx=8, pady=8)
    Button(ctr, text="💾 Enregistrer overlay", command=save_png).pack(side="left", padx=10)

    win.bind("<Configure>", lambda e: refresh())
    refresh()
    root.wait_window(win)
    try: ctr.destroy()
    except Exception: pass


# ---------- pipeline GUI ----------
def lancer_annotation_gui(root, progress_bar, progress_pct=None, status_label=None,
                          min_area: int = 20_000, area_ratio_thresh: float = 0.4):

    last_ui = [0.0]
    def _tick_ui(force=False):
        now = time.perf_counter()
        if force or (now - last_ui[0] >= 0.05):
            try: root.update_idletasks(); root.update()
            except Exception: pass
            last_ui[0] = now

    def set_status(msg: str, fg="orange"):
        if status_label is not None:
            try: status_label.config(text=msg, fg=fg, anchor="w", justify="left", wraplength=600)
            except Exception: pass
        _tick_ui()

    def set_pct(val: int):
        if progress_pct is not None:
            try: progress_pct.config(text=f"{int(max(0, min(100, val)))}%")
            except Exception: pass

    def set_progress(cur: int, tot: int):
        tot = max(int(tot), 1)
        pct = int((int(cur) / tot) * 100)
        try: progress_bar["value"] = pct
        except Exception: pass
        set_pct(pct); _tick_ui()

    try: progress_bar.stop()
    except Exception: pass
    try: progress_bar.config(mode="determinate", maximum=100, value=0)
    except Exception: pass
    set_pct(0)

    BASE = os.path.dirname(os.path.abspath(__file__))
    EXTRACTED_DIR = os.path.join(BASE, "output", "extracted_lames")
    ANNOTATED_DIR = os.path.join(BASE, "output", "annotated")
    os.makedirs(EXTRACTED_DIR, exist_ok=True)
    os.makedirs(ANNOTATED_DIR, exist_ok=True)

    valid_ext = (".tif", ".tiff", ".ndpi", ".svs", ".dcm")
    slides = [os.path.join(EXTRACTED_DIR, f) for f in os.listdir(EXTRACTED_DIR) if f.lower().endswith(valid_ext)]
    slides.sort()

    if not slides:
        messagebox.showwarning("Avertissement", "Aucune lame trouvée dans ‘output/extracted_lames’.", parent=root)
        return

    set_status("🖍️ Annotation globale : préparation…", "orange")
    total = len(slides)

    # 1) première lame (preview persistante)
    first_img  = slides[0]
    base0      = os.path.splitext(os.path.basename(first_img))[0]
    first_json = os.path.join(ANNOTATED_DIR, base0 + "_annotation.json")
    first_png  = os.path.join(ANNOTATED_DIR, base0 + "_preview.png")

    set_progress(0, total); set_status("🔍 Traitement de la première lame…", "orange")

    try:
        nb, img_rgb, mask_bin, overlay_rgb = detect_slide_mask(first_img, first_json,
                                                               min_area=min_area, area_ratio_thresh=area_ratio_thresh)
        set_progress(1, total)
        set_status(f"📁 JSON enregistré  •  1/{total}  •  {os.path.basename(first_json)}  •  contours = {nb}", "lime")
        _show_preview_window(root, base0, img_rgb, mask_bin, overlay_rgb, save_path_png=first_png)
    except Exception as e:
        set_status("❌ Erreur sur la 1ʳᵉ lame", "red")
        messagebox.showerror("Erreur", f"Echec sur la 1ʳᵉ lame :\n{e}", parent=root)
        return

    if total == 1:
        set_progress(100, 100); set_status("✔ Annotation globale terminée ✅", "lime"); return

    # 2) appliquer aux autres ?
    appliquer = messagebox.askyesno("Appliquer à toutes les lames ?",
                                    "Voulez-vous appliquer ce traitement à toutes les autres lames ?",
                                    parent=root)
    if not appliquer:
        try: progress_bar["value"] = 0
        except Exception: pass
        set_pct(0); set_status("⏹️ Annotation annulée par l’utilisateur", "gray"); return

    # 3) boucle reste (sans preview)
    set_status("🔄 Traitement des autres lames…", "orange")
    for idx, img_path in enumerate(slides[1:], start=2):
        base   = os.path.splitext(os.path.basename(img_path))[0]
        out_js = os.path.join(ANNOTATED_DIR, base + "_annotation.json")
        set_status(f"🧩 {idx}/{total}  •  {os.path.basename(img_path)}", "orange"); _tick_ui()
        try:
            nb, _, _, _ = detect_slide_mask(img_path, out_js,
                                            min_area=min_area, area_ratio_thresh=area_ratio_thresh)
            set_status(f"📁 JSON enregistré  •  {idx}/{total}  •  {os.path.basename(out_js)}  •  contours = {nb}", "lime")
        except Exception as e:
            messagebox.showwarning("Avertissement", f"Impossible de traiter {os.path.basename(img_path)}\n{e}", parent=root)
        finally:
            set_progress(idx, total)

    set_progress(100, 100)
    set_status("✔ Annotation globale terminée ✅", "lime")
    messagebox.showinfo("Terminé", "Tous les fichiers JSON possibles ont été générés.", parent=root)
