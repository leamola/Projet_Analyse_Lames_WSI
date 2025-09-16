import os, zipfile, shutil, re

VALID_EXT = (".ndpi", ".svs", ".tif", ".tiff", ".dcm")
MARKER_PATTERN = re.compile(r"(CD\d{1,2}|HES|KI67|PDL1)", re.IGNORECASE)
PATIENT_PATTERN = re.compile(r"(S\d{6,})", re.IGNORECASE)

def extract_patient_marker_from_path(path, selected_markers):
    path = path.replace("\\", "/")
    marker_match = re.search(r"\b(" + "|".join(selected_markers) + r")\b", path, re.IGNORECASE)
    patient_match = PATIENT_PATTERN.search(path)
    marker = marker_match.group(1).upper().replace("-", "") if marker_match else None
    patient = patient_match.group(1).upper() if patient_match else None
    return patient, marker

def detect_markers(zip_path):
    with zipfile.ZipFile(zip_path, 'r') as z:
        all_paths = z.namelist()
        markers = sorted({m.group(1).upper().replace("-", "") for f in all_paths if (m := MARKER_PATTERN.search(f))})
    return markers

def extract_files_from_zip(zip_path, selected_markers, output_dir, progress_callback=None):
    os.makedirs(output_dir, exist_ok=True)
    copied = 0

    if not zipfile.is_zipfile(zip_path):
        print(f"❌ Ce n'est pas un zip valide : {zip_path}")
        return

    with zipfile.ZipFile(zip_path, 'r') as main_zip:
        all_paths = main_zip.namelist()
        to_process = []

        for f in all_paths:
            if f.lower().endswith(".zip"):  # CD3.zip, etc.
                marker = extract_patient_marker_from_path(f, selected_markers)[1]
                if marker:
                    to_process.append(("subzip", f))
            elif f.lower().endswith(VALID_EXT):
                patient, marker = extract_patient_marker_from_path(f, selected_markers)
                if patient and marker:
                    to_process.append(("direct", f))

        total = len(to_process)

        for i, (mode, internal_path) in enumerate(to_process, 1):
            ext = os.path.splitext(internal_path)[1].lower()

            if mode == "subzip":
                try:
                    temp_zip = os.path.join(output_dir, "__temp_sub.zip")
                    with open(temp_zip, "wb") as f_out:
                        f_out.write(main_zip.read(internal_path))

                    # Déduire le patient et le marqueur à partir du chemin externe
                    patient, marker = extract_patient_marker_from_path(internal_path, selected_markers)
                    if not patient or not marker:
                        os.remove(temp_zip)
                        continue

                    if zipfile.is_zipfile(temp_zip):
                        with zipfile.ZipFile(temp_zip, 'r') as subzip:
                            best_file = None
                            best_size = 0

                            for name in subzip.namelist():
                                if not name.lower().endswith(".dcm"):
                                    continue
                                size = subzip.getinfo(name).file_size
                                if size > best_size:
                                    best_file = name
                                    best_size = size

                            if best_file:
                                out_name = f"{patient}_{marker}.dcm"
                                out_path = os.path.join(output_dir, out_name)
                                with subzip.open(best_file) as src, open(out_path, "wb") as dst:
                                    shutil.copyfileobj(src, dst)
                                print(f"✅ Copié : {out_name}")
                                copied += 1

                    os.remove(temp_zip)
                except Exception as e:
                    print(f"[!] Erreur dans sous-archive {internal_path} : {e}")

            elif mode == "direct":
                ext = os.path.splitext(internal_path)[1].lower()
                patient, marker = extract_patient_marker_from_path(internal_path, selected_markers)
                if not patient or not marker:
                    continue
                out_name = f"{patient}_{marker}{ext}"
                out_path = os.path.join(output_dir, out_name)
                try:
                    with main_zip.open(internal_path) as src, open(out_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    print(f"✅ Copié : {out_name}")
                    copied += 1
                except Exception as e:
                    print(f"[!] Erreur copie fichier principal {internal_path} : {e}")

            if progress_callback:
                progress_callback(i, total)

    print(f"\n🎯 Extraction terminée : {copied} fichier(s) copié(s).")
