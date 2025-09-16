# result.py
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime
from tkinter import messagebox, simpledialog


def _fmt_pct(v: float) -> str:
    """50 -> '50p', 50.25 -> '50.25p' (sans traînante)."""
    try:
        v = float(v)
    except Exception:
        return str(v)
    if v.is_integer():
        return f"{int(v)}p"
    return f"{v:.2f}".rstrip("0").rstrip(".") + "p"


def _safe_write_csv(df: pd.DataFrame, out_csv: str, sep=";", encoding="utf-8-sig", index=False, root=None):
    """
    Tente d'écrire le CSV. Si le nom cible est verrouillé (Excel ouvert),
    écrit sous un nom alternatif avec timestamp et avertit l'utilisateur.
    """
    try:
        df.to_csv(out_csv, sep=sep, encoding=encoding, index=index)
        return out_csv, None
    except PermissionError as e:
        # Nom alternatif avec timestamp pour éviter le verrouillage
        base, ext = os.path.splitext(out_csv)
        alt = f"{base}_{datetime.now().strftime('%Y%m%d-%H%M%S')}{ext}"
        try:
            df.to_csv(alt, sep=sep, encoding=encoding, index=index)
            msg = (
                "Le fichier de sortie semble être ouvert (Excel ?) et ne peut pas être écrasé.\n\n"
                f"Fichier initial bloqué :\n{out_csv}\n\n"
                f"Le résultat a été enregistré sous :\n{alt}"
            )
            if root:
                messagebox.showwarning("Fichier verrouillé", msg, parent=root)
            else:
                print("[Avertissement]", msg)
            return alt, e
        except Exception as e2:
            if root:
                messagebox.showerror("Erreur analyse", f"Impossible d'écrire le CSV :\n{out_csv}\n\n{e2}", parent=root)
            else:
                print("[Erreur analyse] Impossible d'écrire le CSV :", out_csv, e2)
            raise
    except Exception as e:
        if root:
            messagebox.showerror("Erreur analyse", f"Impossible d'écrire le CSV :\n{out_csv}\n\n{e}", parent=root)
        else:
            print("[Erreur analyse] Impossible d'écrire le CSV :", out_csv, e)
        raise


def analyser_resultats_cd7(
    root=None,
    progress_bar=None,
    progress_label=None,
    seuil_ratio_cd7=None,     # rétro-compat (ignoré si params.json fournit 'seuil_percent')
    loss_marker=None,         # numérateur
    reference_marker=None,    # dénominateur
    tolerance_percent=2.0     # tolérance en points de %
):
    """
    Calcule par patient : Ratio_% = 100 * (loss / ref),
    puis applique le critère 'autour du seuil' : Suspect si ratio_% <= (seuil_% + tolérance_%).

    Entrées:
      - CSV: output/detected/resume_detection.csv (Fichier; Marqueur; Noyaux_detectés)
      - Params: output/detected/params.json (optionnel)
          Nouveau:
            { "loss_marker": "CD7", "reference_marker": "CD3", "seuil_percent": 10 }
          Ancien:
            { "seuil_cd7_percent": 10 }
    """
    try:
        base_dir     = os.path.dirname(os.path.abspath(__file__))
        detected_dir = os.path.join(base_dir, "output", "detected")
        results_dir  = os.path.join(base_dir, "output", "results")
        os.makedirs(results_dir, exist_ok=True)

        in_csv = os.path.join(detected_dir, "resume_detection.csv")
        params = os.path.join(detected_dir, "params.json")

        if not os.path.exists(in_csv):
            msg = f"Fichier non trouvé :\n{in_csv}"
            if root:
                messagebox.showerror("Erreur", msg, parent=root)
            else:
                print("[Erreur]", msg)
            return

        if progress_label:
            progress_label.config(text="📊 Analyse en cours...")
        if progress_bar:
            progress_bar["value"] = 0

        # --- lire CSV
        try:
            df = pd.read_csv(in_csv, sep=";", encoding="utf-8-sig")
        except UnicodeError:
            df = pd.read_csv(in_csv, sep=";")

        required = {"Fichier", "Marqueur", "Noyaux_detectés"}
        if not required.issubset(df.columns):
            msg = f"Colonnes manquantes dans {in_csv}. Requis : {required}"
            if root:
                messagebox.showerror("Erreur", msg, parent=root)
            else:
                print("[Erreur]", msg)
            return

        # --- paramètres
        seuil_percent = None
        if isinstance(seuil_ratio_cd7, (int, float)):
            seuil_percent = float(seuil_ratio_cd7)

        if os.path.exists(params):
            try:
                with open(params, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if loss_marker is None and "loss_marker" in cfg:
                    loss_marker = str(cfg["loss_marker"])
                if reference_marker is None and "reference_marker" in cfg:
                    reference_marker = str(cfg["reference_marker"])
                if seuil_percent is None and "seuil_percent" in cfg:
                    seuil_percent = float(cfg["seuil_percent"])
                if seuil_percent is None and "seuil_cd7_percent" in cfg:
                    seuil_percent = float(cfg["seuil_cd7_percent"])
                    if loss_marker is None:
                        loss_marker = "CD7"
                    if reference_marker is None:
                        reference_marker = "CD3"
            except Exception:
                pass  # JSON illisible → on garde les défauts

        if loss_marker is None:
            loss_marker = "CD7"
        if reference_marker is None:
            reference_marker = "CD3"
        if seuil_percent is None:
            seuil_percent = 10.0

        # --- liste marqueurs, questions confort
        markers_in_csv = sorted(set(df["Marqueur"].astype(str)))
        if root:
            suggestion = ", ".join(markers_in_csv) if markers_in_csv else "—"
            lm = simpledialog.askstring(
                "Marqueur de PERTE",
                f"Quel marqueur analyser en perte ?\n(Disponibles : {suggestion})",
                initialvalue=str(loss_marker),
                parent=root
            )
            if lm:
                loss_marker = lm.strip()

            rm = simpledialog.askstring(
                "Marqueur de RÉFÉRENCE",
                f"Quel marqueur utiliser en référence ?\n(Disponibles : {suggestion})",
                initialvalue=str(reference_marker),
                parent=root
            )
            if rm:
                reference_marker = rm.strip()

            messagebox.showinfo(
                "Paramètres d’analyse",
                (f"Perte = {loss_marker}\n"
                 f"Référence = {reference_marker}\n"
                 f"Seuil = {seuil_percent:.2f} % (tolérance +{tolerance_percent:.2f} pts)"),
                parent=root
            )

        # --- normaliser Patient
        base_names = df["Fichier"].astype(str).str.replace(r"\.[^.]+$", "", regex=True)
        patients = base_names.copy()
        for mk in markers_in_csv:
            patients = patients.str.replace(f"_{mk}", "", regex=False)
        df["Patient"] = patients

        # --- agrégation
        agg = df.groupby(["Patient", "Marqueur"], as_index=False)["Noyaux_detectés"].sum()
        pivot = agg.pivot(index="Patient", columns="Marqueur", values="Noyaux_detectés").fillna(0)

        if loss_marker not in pivot.columns:
            pivot[loss_marker] = 0
        if reference_marker not in pivot.columns:
            pivot[reference_marker] = 0

        # --- ratio %
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio_percent = np.where(
                pivot[reference_marker] > 0,
                100.0 * pivot[loss_marker] / pivot[reference_marker],
                np.nan
            )

        ratio_col = f"Ratio_{loss_marker}/{reference_marker}_%"
        pivot[loss_marker]      = pivot[loss_marker].astype(int)
        pivot[reference_marker] = pivot[reference_marker].astype(int)
        pivot[ratio_col]        = np.round(ratio_percent, 3)
        pivot["Seuil_%"]        = float(seuil_percent)
        pivot["Tolerance_%"]    = float(tolerance_percent)

        # --- règle “autour du seuil” : suspect si ratio ≤ seuil + tolérance
        def is_suspect(row):
            ref   = row[reference_marker]
            r     = row[ratio_col]
            seuil = row["Seuil_%"]
            tol   = row["Tolerance_%"]

            if ref == 0:
                return True
            if pd.isna(r):
                return False
            if r > 100.0:
                return False
            return r <= (seuil + tol)

        pivot["Suspect"] = pivot.apply(is_suspect, axis=1)

        # --- sauvegarde : inclure le seuil dans le nom
        out_name = f"analyse_{loss_marker}_vs_{reference_marker}_seuil_{_fmt_pct(seuil_percent)}.csv"
        out_csv  = os.path.join(results_dir, out_name)

        written, _ = _safe_write_csv(pivot.reset_index(), out_csv, root=root)

        if progress_bar:
            progress_bar["value"] = 100
        if progress_label:
            progress_label.config(text="✅ Analyse terminée")
        if root:
            messagebox.showinfo("Analyse", f"CSV généré :\n{written}", parent=root)
        else:
            print(f"[OK] Analyse sauvegardée : {written}")

    except Exception as e:
        if root:
            messagebox.showerror("Erreur analyse", str(e), parent=root)
        else:
            print("[Erreur analyse]", e)
