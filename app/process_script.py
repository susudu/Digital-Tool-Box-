# app/process_script.py
import sys
import os
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from pathlib import Path
from soundscapy.plotting import density_plot
import soundscapy.surveys as surveys
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = ROOT / "uploads"
RESULT_DIR = ROOT / "results"
METAFILE = ROOT / "results_meta.json"

locations = {}

# =====================================================
# GLOBAL NORMALIZATION MAXIMUM
# =====================================================
FIXED_MAX = 7.0   # freely change to 6, 6.5, 7, etc.

def read_meta():
    if not METAFILE.exists(): 
        return {}
    return json.loads(METAFILE.read_text())

def write_meta(meta):
    METAFILE.write_text(json.dumps(meta))

def update_meta(file_id, **kwargs):
    meta = read_meta()
    if file_id not in meta:
        return
    meta[file_id].update(kwargs)
    write_meta(meta)

# =====================================================
# CORE COMPUTATION
# =====================================================
def calculate_coordinates(e, v, p, ca, u, m, a, ch):
     """Compute Pleasantness (P) and Eventfulness (E) based on formula."""
     P = (p - a) + np.cos(np.deg2rad(45)) * (ca - ch) + np.cos(np.deg2rad(45)) * (v - m)
     E = (e - u) + np.cos(np.deg2rad(45)) * (ch - ca) + np.cos(np.deg2rad(45)) * (v - m)
     return P, E

def compute_P_E(locations):
     """Compute raw P and E values (no normalization)."""
     P_values, E_values = [], []
     for _, values in locations.items():
          e, v, p, ca, u, m, a, ch = values
          P, E = calculate_coordinates(e, v, p, ca, u, m, a, ch)
          P_values.append(P)
          E_values.append(E)
     return np.array(P_values), np.array(E_values)

# =====================================================
# FIXED-MAX SIGNED NORMALIZATION ( −1 to 1 )
# =====================================================
def signed_normalize_fixed(arr, fixed_max):
     
     """
     Normalize using a *fixed chosen maximum*:
      +fixed_max → +1.0
      -fixed_max → -1.0

     This ensures all datasets share the same scale.
     """
     arr = np.array(arr, dtype=float)
     norm_arr = arr / fixed_max

     # Limit values within [-1, 1] just in case
     norm_arr = np.clip(norm_arr, -1, 1)
     return norm_arr
     
# ===============================================================================
# PLOTTING FUNCTION (for normalized plot only) (AXIS FIXED TO ±1, ENHANCED STYLE)
# ===============================================================================
def plot_PE(ax, P_values, E_values, locations, SCENE_STYLES, SCENE_LABELS, TITLE):
    # Ensure P_values/E_values are lists
    P_values = list(P_values) if isinstance(P_values, (np.ndarray, list, tuple)) else [P_values]
    E_values = list(E_values) if isinstance(E_values, (np.ndarray, list, tuple)) else [E_values]

    # Match number of scenes
    scene_list = list(locations.keys())
    n_scenes = len(scene_list)
    if len(P_values) != n_scenes or len(E_values) != n_scenes:
        # Pad/truncate safely
        P_values = (P_values + [0]*n_scenes)[:n_scenes]
        E_values = (E_values + [0]*n_scenes)[:n_scenes]

    used_labels = set()
    for i, location in enumerate(scene_list):
        style = SCENE_STYLES.get(location, {'color': 'gray', 'marker': 'o'})
        label = SCENE_LABELS.get(location, location) if location not in used_labels else None
        used_labels.add(location)
        ax.scatter(P_values[i], E_values[i],
                   marker=style['marker'],
                   color=style['color'],
                   label=label,
                   s=45, alpha=0.8,
                   edgecolor='black', linewidth=0.6, zorder=3)

    # # Connect points if needed
    # if TITLE == "VR Group: View - Away":
    #     coordinates_dict = {scene: (P_values[i], E_values[i]) for i, scene in enumerate(scene_list)}
    #     pairs_to_connect = [
    #         ('VR-E1-0v', 'VR-E1-0a'), ('VR-E1-1v', 'VR-E1-1a'),
    #         ('VR-E2-0v', 'VR-E2-0a'), ('VR-E2-1v', 'VR-E2-1a'),
    #         ('VR-W1-0v', 'VR-W1-0a'), ('VR-W1-1v', 'VR-W1-1a'),
    #         ('VR-W2-0v', 'VR-W2-0a'), ('VR-W2-1v', 'VR-W2-1a'),
    #     ]
    #     for loc1, loc2 in pairs_to_connect:
    #         if loc1 in coordinates_dict and loc2 in coordinates_dict:
    #             P1, E1 = coordinates_dict[loc1]
    #             P2, E2 = coordinates_dict[loc2]
    #             ax.plot([P1, P2], [E1, E2], color='gray', linestyle='-', linewidth=0.8, alpha=0.5, zorder=2)
    # else:
    #     for i in range(0, len(P_values)-1, 2):
    #         ax.plot([P_values[i], P_values[i+1]], [E_values[i], E_values[i+1]],
    #                 linestyle='-', color='gray', linewidth=0.8, alpha=0.5, zorder=2)

    # Axes & grid
    ax.set_xlim(-1.05, 1.05)
    ax.set_ylim(-1.05, 1.05)
    ax.set_xticks(np.arange(-1, 1.05, 0.25))
    ax.set_yticks(np.arange(-1, 1.05, 0.25))
    ax.tick_params(axis='both', labelsize=8)
    ax.grid(True, linestyle='--', linewidth=0.5, alpha=1)
    ax.set_aspect('equal', 'box')
    ax.axhline(0, color='black', linewidth=1.5, alpha=0.4, zorder=2)
    ax.axvline(0, color='black', linewidth=1.5, alpha=0.4, zorder=2)

    # Quadrant labels
    ax.text(-0.56, 0.56, '(Chaotic)', color='gray', fontsize=9, ha='center', va='center', alpha=0.7 , fontweight='bold', fontstyle='italic')
    ax.text(0.56, 0.56, '(Vibrant)', color='gray', fontsize=9, ha='center', va='center', alpha=0.7 , fontweight='bold', fontstyle='italic')
    ax.text(-0.56, -0.56, '(Monotonous)', color='gray', fontsize=9, ha='center', va='center', alpha=0.7 , fontweight='bold', fontstyle='italic')
    ax.text(0.56, -0.56, '(Calm)', color='gray', fontsize=9, ha='center', va='center', alpha=0.7 , fontweight='bold', fontstyle='italic')

    ax.set_title("Fixed-Max Normalized (−1 to 1)", fontsize=10, fontweight='bold')
    ax.set_xlabel("ISOPleasant", fontsize=9)
    ax.set_ylabel("ISOEventful", fontsize=9)

def show_normalized_scene_plot(TITLE, P_norm, E_norm, locations, SCENE_STYLES, SCENE_LABELS):
    # Bigger figure for Streamlit
    fig, ax = plt.subplots(figsize=(6,6))
    plt.suptitle(TITLE, fontsize=12, fontweight='bold', y=0.95)

    # Plot the points
    plot_PE(ax, P_norm, E_norm, locations, SCENE_STYLES, SCENE_LABELS, TITLE)

    # ----- LEGEND OUTSIDE -----
    handles, labels = ax.get_legend_handles_labels()

    fig.legend(
        handles, labels,
        title="Scenes",
        loc="upper left",
        bbox_to_anchor=(1.02, 1),   # moves legend outside
        borderaxespad=0,
        fontsize=8,
    )

    # Add space on the right so the legend fits
    fig.subplots_adjust(right=0.78)

    return fig

def main():
    if len(sys.argv) < 3:
        print("Usage: process_script.py <file_path> <file_id>")
        sys.exit(1)

    file_path = sys.argv[1]
    file_id = sys.argv[2]

    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        update_meta(file_id, status="error")
        print("Error reading file:", e)
        return
      
    # =====================================================
    # CONFIGURATION
    # =====================================================
    TITLE = "East Side – SW and VR Groups: Façade Effect"
    
    # =====================================================
    # LOAD DATA
    # =====================================================
    df_areas = df.set_index("scene").T
    locations = {area: tuple(df_areas.loc[area]) for area in df_areas.index}
    
    # Compute raw values
    P_raw, E_raw = compute_P_E(locations)
    
    # Apply fixed normalization
    P_norm = signed_normalize_fixed(P_raw, FIXED_MAX)
    E_norm = signed_normalize_fixed(E_raw, FIXED_MAX)
    
    # =====================================================
    # SCENE STYLE & LABEL DEFINITIONS
    # =====================================================

    SCENE_STYLES = {
        'SW-E1-0': {'color': '#5da5c3', 'marker': 'o'},
        'SW-E1-1': {'color': '#3b5b92', 'marker': 'o'},
        'VR-E1-0v': {'color': '#9dcf75', 'marker': 'o'},
        'VR-E1-1v': {'color': '#66a61e', 'marker': 'o'},
        'VR-E1-0a': {'color': '#f6b686', 'marker': 'o'},
        'VR-E1-1a': {'color': '#e6ab02', 'marker': 'o'},
        'SW-E2-0': {'color': '#5da5c3', 'marker': 'X'},
        'SW-E2-1': {'color': '#3b5b92', 'marker': 'X'},
        'VR-E2-0v': {'color': '#9dcf75', 'marker': 'X'},
        'VR-E2-1v': {'color': '#66a61e', 'marker': 'X'},
        'VR-E2-0a': {'color': '#f6b686', 'marker': 'X'},
        'VR-E2-1a': {'color': '#e6ab02', 'marker': 'X'},
    }
    
    SCENE_LABELS = {
         'SW-E1-0':  'SW – façade still | noiseless',
         'SW-E1-1':  'SW – façade still | noise',
         'VR-E1-0v': 'VR – façade still | noiseless-view',
         'VR-E1-1v': 'VR – façade still | noise-view',
         'VR-E1-0a': 'VR – façade still | noiseless-away',
         'VR-E1-1a': 'VR – façade still | noise-away',
         'SW-E2-0':  'SW – façade move | noiseless',
         'SW-E2-1':  'SW – façade move | noise',
         'VR-E2-0v': 'VR – façade move | noiseless-view',
         'VR-E2-1v': 'VR – façade move | noise-view',
         'VR-E2-0a': 'VR – façade move | noiseless-away',
         'VR-E2-1a': 'VR – façade move | noise-away',
    } 

    plots = []
    preview_html = ""

    # === EXCEL DATA PREVIEW ===
    try:
        preview_df = df.head(10)   # first 10 rows
        preview_html += "<h3>Data Preview</h3>"
        preview_html += preview_df.to_html(border=1)
    except Exception as e:
        print("data preview error:", e)

    # === Generate PLOT 1 ===
    try:
      fig = show_normalized_scene_plot(TITLE,P_norm=P_norm,E_norm=E_norm,locations=locations,SCENE_STYLES=SCENE_STYLES,SCENE_LABELS=SCENE_LABELS)
      f1 = f"{file_id}_plot1.png"
      out1 = RESULT_DIR / f1
      RESULT_DIR.mkdir(exist_ok=True)
      fig.savefig(out1, bbox_inches="tight", dpi=200)
      plt.close(fig)
      plots.append(f1)
      #preview_html += f"<div><strong>Preview:</strong><br><img src='/result/{file_id}/{f1}' style='max-width:360px'></div>"
    except Exception as e:
      print("plot1 error", e)

    # # === EXAMPLE PLOT 2 === (scatter of first two numeric cols if exist)
    # try:
    #     if numeric.shape[1] >= 2:
    #         fig, ax = plt.subplots(figsize=(6,4))
    #         x = numeric.columns[0]
    #         y = numeric.columns[1]
    #         ax.scatter(numeric[x], numeric[y], alpha=0.7)
    #         ax.set_xlabel(x); ax.set_ylabel(y)
    #         ax.set_title(f"{x} vs {y}")
    #         f2 = f"{file_id}_plot2.png"
    #         out2 = RESULT_DIR / f2
    #         fig.savefig(out2, bbox_inches="tight", dpi=200)
    #         plt.close(fig)
    #         plots.append(f2)
    # except Exception as e:
    #     print("plot2 error", e)

    # === Save JSON summary ===
    meta = read_meta()
    if file_id not in meta:
        meta[file_id] = {}
    meta[file_id].update({
        "file_id": file_id,
        "filename": Path(file_path).name,
        "status": "done",
        "processed_at": datetime.utcnow().isoformat(),
        "plots": plots,
        "preview_html": preview_html
    })
    write_meta(meta)

    # Optionally remove the uploaded file to free disk space
    try:
        os.remove(file_path)
    except Exception:
        pass

if __name__ == "__main__":
    main()
