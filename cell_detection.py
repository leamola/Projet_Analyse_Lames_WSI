import os, time, gc, json
import numpy as np
import cv2
import openslide
from skimage.color import rgb2hed
import pandas as pd

# ===================== Dossiers =====================
SLIDES_DIR = r"D:\QuPathProjects\PathologyToolbox\output\extracted_lames"
JSON_DIR   = r"D:\QuPathProjects\PathologyToolbox\output\annotated"
OUTPUT_DIR = r"D:\QuPathProjects\PathologyToolbox\output\detected"
CSV_OUTPUT = os.path.join(OUTPUT_DIR, "resume_detection.csv")

# ===================== Paramètres ====================
ALLOWED_EXT   = (".ndpi", ".svs", ".tif", ".tiff")
LEVEL         = 1
SEUIL_DAB     = 0.02

MIN_AREA      = 10
SMALL_AREA    = 80
MAX_AREA      = 10_000_000_000

TIMEOUT_S     = 240
MAX_CONTOURS  = 200_000

# — Quand un ROI est “énorme” → on passe en mode tuilé (affichage bord violet rapide)
HUGE_ROI_PIXELS  = 1_000_000   # w*h >= seuil → watershed par tuiles + bords violets

# — Si un ROI normal produit trop de segments → affichage bord violet (pas de contours verts)
DRAW_LIMIT_ROI   = 6000

# — Tuilage (plein résolution, pas de downscale)
TILE_SIZE        = 1024
TILE_OVERLAP     = 96          # chevauchement
EDGE_THICKNESS   = 1           # épaisseur du liseré de bord (violet)
SEED_MIN_DIST    = 2
SEED_THR_RATIO   = 0.28
SEED_MAX_TILE    = 12000
SEED_MAX_FULL    = 30000

# I/O
PNG_COMPRESSION  = 1  # 0–3 = rapide

# Couleurs BGR
COL_GREEN   = (0, 255, 0)      # contours (petits ROIs)
COL_VIOLET  = (255, 0, 255)    # bords watershed “rapide”
COL_YELLOW  = (255, 255, 0)    # cadre info ROI chargé
COL_RED     = (0, 0, 255)      # contour zone JSON

cv2.setUseOptimized(True)
cv2.setNumThreads(0)

# --- Affichage "traitement long" basé sur le temps écoulé ---
LONG_NOTE_FRAC = 0.45    # affiche la note dès que t >= 45% du TIMEOUT
LONG_NOTE_MIN_S = 35     # et au moins 35s passées (pour éviter les faux positifs)

# ===================== Helpers =======================
def _read_slide_lowres(path, level=1):
    slide = openslide.OpenSlide(path)
    lev = min(level, slide.level_count - 1)
    dims = slide.level_dimensions[lev]
    img = np.array(slide.read_region((0, 0), lev, dims).convert("RGB"), dtype=np.uint8)
    slide.close()
    return img

def _binary_dab_tiled(img_rgb, mask_zone=None, seuil=SEUIL_DAB, tile=1536):
    H, W = img_rgb.shape[:2]
    out = np.zeros((H, W), np.uint8)
    for y in range(0, H, tile):
        for x in range(0, W, tile):
            y2, x2 = min(y + tile, H), min(x + tile, W)
            if mask_zone is not None and mask_zone[y:y2, x:x2].max() == 0:
                continue
            bf  = (img_rgb[y:y2, x:x2].astype(np.float32) / 255.0)
            dab = rgb2hed(bf)[:, :, 2].astype(np.float32)
            tmp = (dab > seuil).astype(np.uint8) * 255
            if mask_zone is not None:
                tmp[mask_zone[y:y2, x:x2] == 0] = 0
            out[y:y2, x:x2] = tmp
    return out

def _maxima_seeds(dist, min_distance=SEED_MIN_DIST, thr_ratio=SEED_THR_RATIO, max_seeds=None, p=35):
    if dist.dtype != np.float32:
        dist = dist.astype(np.float32)
    v = dist[dist > 0]
    thr1 = float(dist.max()) * float(thr_ratio)
    thr2 = float(np.percentile(v, p)) if v.size else 0.0
    thr  = max(1e-6, min(thr1, thr2))
    mask = dist > thr
    if not np.any(mask):
        return np.zeros_like(dist, dtype=np.uint8)
    k = 2 * int(min_distance) + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    dmax = cv2.dilate(dist, kernel)
    peaks = (dist == dmax) & mask
    if max_seeds is not None:
        ys, xs = np.nonzero(peaks)
        if ys.size > max_seeds:
            vals = dist[ys, xs]
            idx  = np.argpartition(vals, -max_seeds)[-max_seeds:]
            sel  = np.zeros_like(peaks, dtype=np.uint8)
            sel[ys[idx], xs[idx]] = 255
            return sel
    return (peaks.astype(np.uint8) * 255)

def _watershed_full(roi_bin):
    """Watershed plein format → contours verts ET edges (mask -1)."""
    dist = cv2.distanceTransform(roi_bin, cv2.DIST_L2, 5)
    seeds = _maxima_seeds(dist, max_seeds=SEED_MAX_FULL)
    _, markers = cv2.connectedComponents(seeds)
    markers = cv2.watershed(cv2.cvtColor(roi_bin, cv2.COLOR_GRAY2BGR), markers)
    return markers  # int32, -1 sur les bords entre régions

def _draw_edges_into(output, x, y, edge_mask, color=COL_VIOLET, thick=EDGE_THICKNESS):
    """Colorie rapidement les bords dans output[y:y+h, x:x+w]."""
    if thick > 1:
        edge_mask = cv2.dilate(edge_mask, cv2.getStructuringElement(cv2.MORPH_RECT, (thick, thick)))
    roi = output[y:y+edge_mask.shape[0], x:x+edge_mask.shape[1]]
    m   = edge_mask > 0
    roi[m] = color

def _watershed_edges_tiled_and_count(roi_bin, tile=TILE_SIZE, overlap=TILE_OVERLAP):
    """
    Watershed par tuiles plein format.
    - Retourne edge_mask global (uint8, 0/255) et n_cells (comptage dé-doublonné).
    - Dé-doublonnage via centroïdes gardés UNIQUEMENT dans le cœur de tuile (on ignore l’overlap).
    """
    h, w = roi_bin.shape
    edges = np.zeros((h, w), np.uint8)
    n_cells = 0

    step = max(1, tile - overlap)
    margin = max(0, overlap // 2)  # zone exclue pour le comptage aux bords

    for ty in range(0, h, step):
        for tx in range(0, w, step):
            y2, x2 = min(ty + tile, h), min(tx + tile, w)
            sub = roi_bin[ty:y2, tx:x2]
            if sub.max() == 0:
                continue

            mk = _watershed_full(sub)
            # edges locaux
            edge_local = (mk == -1).astype(np.uint8) * 255
            patch = edges[ty:y2, tx:x2]
            np.maximum(patch, edge_local, out=patch)

            # comptage : centroïdes dans le cœur
            y1_in = ty + margin; x1_in = tx + margin
            y2_in = max(y1_in, y2 - margin); x2_in = max(x1_in, x2 - margin)
            if y1_in >= y2_in or x1_in >= x2_in:
                y1_in, x1_in, y2_in, x2_in = ty, tx, y2, x2  # fallback si tuile trop petite

            labels = np.unique(mk)
            for lid in labels:
                if lid <= 1:
                    continue
                m = (mk == lid).astype(np.uint8)
                M = cv2.moments(m)
                if M["m00"] == 0:
                    continue
                cx = int(M["m10"] / M["m00"]) + tx
                cy = int(M["m01"] / M["m00"]) + ty
                if (x1_in <= cx < x2_in) and (y1_in <= cy < y2_in):
                    n_cells += 1

    return edges, n_cells

# ===================== Pipeline =======================
def detecter_noyaux_dab(root=None, progress_bar=None, progress_label=None):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_slides = sorted([f for f in os.listdir(SLIDES_DIR) if f.lower().endswith(ALLOWED_EXT)])
    csv_rows = []

    # utilité pour afficher 1 ou 2 lignes sous la barre
    def set_status(main_text, extra_line=None):
        if progress_label:
            progress_label.config(text=f"{main_text}\n{extra_line}" if extra_line else str(main_text))

    if progress_bar:
        progress_bar["value"] = 0
        progress_bar["maximum"] = len(all_slides)

    for idx, filename in enumerate(all_slides):
        t0 = time.time()
        print(f"\n→ {idx+1}/{len(all_slides)} : {filename}")

        image_path = os.path.join(SLIDES_DIR, filename)
        json_path  = os.path.join(JSON_DIR, os.path.splitext(filename)[0] + "_annotation.json")
        output_path = os.path.join(OUTPUT_DIR, os.path.splitext(filename)[0] + "_detected_masked.png")

        # NOTE basée sur le temps écoulé
        def long_note_if_any():
            elapsed = time.time() - t0
            if elapsed >= max(LONG_NOTE_MIN_S, TIMEOUT_S * LONG_NOTE_FRAC):
                # <<< message demandé >>>
                return "Lame très chargée en cellules marquées — observation plus longue..."
            return None

        def ui_tick(extra=None):
            if progress_bar:   progress_bar["value"] = idx + 1
            set_status(f"{idx+1}/{len(all_slides)} lames traitées", extra)
            if root:
                root.update_idletasks(); root.update()

        try:
            if not os.path.exists(json_path):
                print("⚠ Masque JSON introuvable — skip")
                ui_tick();  continue

            # 1) Lecture lame
            try:
                img_rgb = _read_slide_lowres(image_path, level=LEVEL)
            except Exception as e:
                print(f"⚠ OpenSlide KO : {e}")
                ui_tick();  continue

            H, W = img_rgb.shape[:2]

            # MAJ status en fonction du temps déjà passé
            extra_line = long_note_if_any()
            ui_tick(extra=extra_line)

            if time.time() - t0 > TIMEOUT_S:
                print("⏱️ Timeout après lecture → skip")
                ui_tick(extra=extra_line);  continue

            # 2) Masque zone JSON
            mask_zone = np.zeros((H, W), dtype=np.uint8)
            with open(json_path, "r", encoding="utf-8") as f:
                annotations = json.load(f)
            for ann in annotations:
                coords = np.array(ann["geometry"]["coordinates"][0], dtype=np.float32)
                coords[:, 0] = np.clip(coords[:, 0], 0, W - 1)
                coords[:, 1] = np.clip(coords[:, 1], 0, H - 1)
                cv2.fillPoly(mask_zone, [coords.astype(np.int32)], 1)

            # 3) DAB binaire (tuiles)
            binary_dab = _binary_dab_tiled(img_rgb, mask_zone=mask_zone, seuil=SEUIL_DAB, tile=1536)

            # 4) Contours bruts
            contours, _ = cv2.findContours(binary_dab, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if len(contours) > MAX_CONTOURS:
                print(f"⚠ {len(contours)} contours (très bruyant) → skip rapide")
                ui_tick(extra=extra_line);  continue

            output = img_rgb.copy()
            n_dab_detected = 0

            # 5) Boucle contours
            for cnt in contours:
                # si on passe le seuil "long", on affiche la note (une seule fois)
                if extra_line is None:
                    maybe = long_note_if_any()
                    if maybe:
                        extra_line = maybe
                        ui_tick(extra=extra_line)

                if time.time() - t0 > TIMEOUT_S:
                    print("⏱️ Timeout en traitement → sauvegarde partielle et on passe")
                    break

                area = cv2.contourArea(cnt)
                if not (MIN_AREA < area < MAX_AREA):
                    continue

                if area <= SMALL_AREA:
                    cv2.drawContours(output, [cnt], -1, COL_GREEN, 1)
                    n_dab_detected += 1
                    continue

                x, y, w, h = cv2.boundingRect(cnt)
                roi = binary_dab[y:y+h, x:x+w]

                if w * h >= HUGE_ROI_PIXELS:
                    edge_mask, n_cells = _watershed_edges_tiled_and_count(roi, tile=TILE_SIZE, overlap=TILE_OVERLAP)
                    _draw_edges_into(output, x, y, edge_mask, color=COL_VIOLET, thick=EDGE_THICKNESS)
                    n_dab_detected += n_cells
                    cv2.rectangle(output, (x, y), (x + w, y + h), COL_YELLOW, 1)
                    continue

                markers = _watershed_full(roi)
                labels = np.unique(markers)
                num_labels = int(np.sum(labels > 1))

                if num_labels > DRAW_LIMIT_ROI:
                    edge_mask = (markers == -1).astype(np.uint8) * 255
                    _draw_edges_into(output, x, y, edge_mask, color=COL_VIOLET, thick=EDGE_THICKNESS)
                    n_dab_detected += num_labels
                    cv2.rectangle(output, (x, y), (x + w, y + h), COL_YELLOW, 1)
                else:
                    for lid in labels:
                        if lid <= 1:
                            continue
                        m = (markers == lid).astype(np.uint8)
                        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                        for sc in cs:
                            sa = cv2.contourArea(sc)
                            if MIN_AREA < sa < MAX_AREA:
                                sc[:, 0, 0] += x
                                sc[:, 0, 1] += y
                                cv2.drawContours(output, [sc], -1, COL_GREEN, 1)
                                n_dab_detected += 1

            # 6) Contour ROUGE de la zone
            contours_json, _ = cv2.findContours(mask_zone, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(output, contours_json, -1, COL_RED, 3)
            cv2.imwrite(output_path, cv2.cvtColor(output, cv2.COLOR_RGB2BGR),
                        [cv2.IMWRITE_PNG_COMPRESSION, PNG_COMPRESSION])

            # 7) CSV
            marker = "CD3" if "CD3" in filename.upper() else "CD7" if "CD7" in filename.upper() else "?"
            area_mask = int(np.count_nonzero(mask_zone))
            percent_detected = round((n_dab_detected / area_mask) * 100, 3) if area_mask > 0 else 0.0
            csv_rows.append({
                "Fichier": filename,
                "Marqueur": marker,
                "Niveau": LEVEL,
                "Seuil_DAB": SEUIL_DAB,
                "Min_Area": MIN_AREA,
                "Max_Area": MAX_AREA,
                "Noyaux_detectés": n_dab_detected,
                "Surface_masquée (px)": area_mask,
                "Densité_noyaux (%)": percent_detected
            })

            print(f"   ✓ OK en {time.time() - t0:.1f}s — noyaux: {n_dab_detected}")

        except Exception as e:
            print(f"⚠ Erreur avec {filename} : {e}")

        # UI + ménage
        ui_tick(extra=extra_line if 'extra_line' in locals() else None)
        for v in ("img_rgb", "binary_dab", "mask_zone", "output", "roi"):
            if v in locals(): locals()[v] = None
        gc.collect()

    # 8) Sauvegarde CSV
    try:
        pd.DataFrame(csv_rows).to_csv(CSV_OUTPUT, sep=';', index=False)
        print(f"\n📄 Résumé CSV : {CSV_OUTPUT}")
    except Exception as e:
        print(f"❌ Erreur CSV : {e}")

    if progress_label:
        progress_label.config(text="✅ Détection terminée")
