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
import re
import settings
import requests

ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = ROOT / "uploads"
RESULT_DIR = ROOT / "results"
METAFILE = ROOT / "results_meta.json"

locations = {}

# =====================================================
# GLOBAL NORMALIZATION MAXIMUM
# =====================================================
FIXED_MAX = 7.0   # freely change to 6, 6.5, 7, etc.

def get_paired_toggle():
    try:
        r = requests.get("https://digital-tool-box-ui.onrender.com/debug_toggle", timeout=3)
        return r.json().get("paired_connectors", False)
    except:
        return False

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

def data_preprocessing(df):
    # clean the ID column in-place
    df['ID'] = df['ID'].str.replace(r'Assessment \d+', 'Assessment ', regex=True)

    # rename the cleaned column
    df = df.rename(columns={'ID': 'scene'})
    
    # automatically select columns that match the regex
    pattern = r"^Category"   # <-- change this to your regex
    category_cols = [col for col in df.columns if re.search(pattern, col)]

    category_maps = {}

    for col in category_cols:
        df[col] = df[col].astype("category")
        df[col + "_code"] = df[col].cat.codes
        category_maps[col] = dict(enumerate(df[col].cat.categories))

    # combine scene + all category_codes
    code_cols = [col + "_code" for col in category_cols]
    df["scene"] = df["scene"].astype(str) + "_" + df[code_cols].astype(str).agg("_".join, axis=1)

    # remove original category columns + code columns
    df = df.drop(columns=category_cols + code_cols)

    # set scene as index and transpose
    df_pivot = df.set_index("scene").T
    df_pivot = df_pivot.rename_axis("scene").reset_index()
 
    # arrange the rows according to the order used in calculate_coordinates,compute_P_E functions
    desired_order = ["eventful", "vibrant", "pleasant", "calm", "uneventful", "monotonous", "annoying", "chaotic"]
    order_col = "scene"
    df_pivot[order_col] = pd.Categorical(df_pivot[order_col], categories=desired_order, ordered=True)
    df_pivot = df_pivot.sort_values(order_col).set_index(order_col)
    
    # after transpose, index rename to "scene"
    df_pivot = df_pivot.rename_axis("scene").reset_index()
    return df_pivot, category_maps

def restore_category_from_scene(scene, category_maps):
    parts = scene.split("_")

    if len(parts) < 2:
        return scene  # nothing to restore

    base = parts[0]
    code_strings = parts[1:]  # all numeric category codes

    decoded_values = []

    # Decode each category code
    for (_, cat_map), code_str in zip(category_maps.items(), code_strings):
        code = int(code_str)
        decoded_values.append(cat_map.get(code, "unknown"))

    # Combine category values with +
    cat_combined = "+".join(decoded_values)
    print(type(cat_combined))

    restored = f"{base}_{cat_combined}"
    return restored

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

    paired_on = get_paired_toggle()

    # Connect points if toggle button on
    if paired_on:
        print(paired_on,"PAIRED CONNECTORS: ON — drawing lines")
        for i in range(0, len(P_values)-1, 2):
            ax.plot([P_values[i], P_values[i+1]], [E_values[i], E_values[i+1]],
                    linestyle='-', color='gray', linewidth=0.8, alpha=0.5, zorder=2)
    else:
        print(paired_on,"PAIRED CONNECTORS: OFF — drawing lines")
        pass

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

def scene_scatter_plot(TITLE_SC, P_norm, E_norm, locations, SCENE_STYLES, SCENE_LABELS):
    # Bigger figure for Streamlit
    fig, ax = plt.subplots(figsize=(6,6))
    plt.suptitle(TITLE_SC, fontsize=12, fontweight='bold', y=0.95)

    # Plot the points
    plot_PE(ax, P_norm, E_norm, locations, SCENE_STYLES, SCENE_LABELS, TITLE_SC)

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

def scene_distrib_plot(df_row,TITLE_DS):
    df_copy = df_row.copy()
    df_selected = df_copy.drop("ID", axis = 1)

    # Rename columns
    column_map = {
        'pleasant': 'PAQ1',
        'vibrant': 'PAQ2',
        'eventful': 'PAQ3',
        'chaotic': 'PAQ4',
        'annoying': 'PAQ5',
        'monotonous': 'PAQ6',
        'uneventful': 'PAQ7',
        'calm': 'PAQ8'
    }
    df_selected = df_selected.rename(columns=column_map)
    
    # --- Add ISO coordinates ---
    valid_data = surveys.add_iso_coords(df_selected)
    
    # # --- Combine all categories ---
    category_cols = [col for col in valid_data.columns if col.startswith("Category")]
    valid_data["Condition"] = valid_data[category_cols].astype(str).agg("+".join, axis=1)
    
    # --- FIXED STATIC ORDERING ---
    unique_conditions = sorted(valid_data["Condition"].unique())
    
    # --- FIXED COLOR PALETTE (tab10 based, reproducible) ---
    cmap = plt.cm.tab10
    palette = {
        cond: cmap(i / len(unique_conditions))
        for i, cond in enumerate(unique_conditions)
    }

    # Create a figure and axis
    fig, ax = plt.subplots(figsize=(6,6))
    plt.suptitle(TITLE_DS, fontsize=12, fontweight='bold', y=0.95)

    # --- Plot the points---
    density_plot(
        valid_data,
        title=TITLE_DS,
        hue="Condition",
        simple_density=True,
        incl_scatter=True,
        diagonal_lines=True,
        fill=True,
        palette=palette,
        ax=ax
    )
    
    # Remove automatic axis legend to avoid duplicate
    if ax.get_legend() is not None:
        ax.get_legend().remove()
    
    # --- FIX LEGEND ORDER OUTSIDE ---
    handles, labels = ax.get_legend_handles_labels() 
    ordered_handles = [handles[labels.index(c)] for c in unique_conditions]
    ordered_labels = unique_conditions

    fig.legend(
        ordered_handles, ordered_labels,
        title="Conditions",
        loc="upper left",
        bbox_to_anchor=(1.02, 1),   # moves legend outside
        borderaxespad=0,
        fontsize=8,
    )

    # Add space on the right so the legend fits
    fig.subplots_adjust(right=0.78)

    #ax.legend(ordered_handles,ordered_labels, loc="lower left", fontsize=8)
    #plt.tight_layout()

    return fig

def main():
    if len(sys.argv) < 3:
        print("Usage: process_script.py <file_path> <file_id>")
        sys.exit(1)

    file_path = sys.argv[1]
    file_id = sys.argv[2]

    try:
    # =====================================================
    # LOAD DATA
    # =====================================================
        df_row = pd.read_excel(file_path)
        df,category_map = data_preprocessing(df_row)
        df.columns = [restore_category_from_scene(col, category_map) for col in df.columns]
        df_areas = df.set_index("scene").T
        locations = {area: tuple(df_areas.loc[area]) for area in df_areas.index}
    except Exception as e:
        update_meta(file_id, status="error")
        print("Error reading file:", e)
        return
      
    # =====================================================
    # CONFIGURATION
    # =====================================================
    TITLE_SC = "Test All Scatter Plots"
    TITLE_DS = "Test Distribution Plots"
    
    # Compute raw values
    P_raw, E_raw = compute_P_E(locations)
    
    # Apply fixed normalization
    P_norm = signed_normalize_fixed(P_raw, FIXED_MAX)
    E_norm = signed_normalize_fixed(E_raw, FIXED_MAX)

    # =====================================================
    # SCENE STYLE & LABEL DEFINITIONS
    # =====================================================
    COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', 
    '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', 
    '#bcbd22', '#17becf']
    MARKERS = ['o', 'X', 's', 'D', '^', 'v', '<', '>', 'P', '*']
    
    def build_scene_styles(scene_labels):
        styles = {}
        for i, label in enumerate(scene_labels):
            styles[label] = {
                "color": COLORS[i % len(COLORS)],
                "marker": MARKERS[i % len(MARKERS)]
            }
        return styles
        
    def build_scene_labels(columns):
        labels = {}
        for col in columns:
            labels[col] = col
        # # readable label replace "-" with " | " 
        #     human = col.replace("-", " | ")
        #     labels[col] = human
        return labels
    
    SCENE_LABELS = build_scene_labels(df.columns)
    SCENE_STYLES = build_scene_styles(SCENE_LABELS.keys())

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
        fig = scene_scatter_plot(TITLE_SC,P_norm=P_norm,E_norm=E_norm,locations=locations,SCENE_STYLES=SCENE_STYLES,SCENE_LABELS=SCENE_LABELS)
        f1 = f"{file_id}_plot1.png"
        out1 = RESULT_DIR / f1
        RESULT_DIR.mkdir(exist_ok=True)
        fig.savefig(out1, bbox_inches="tight", dpi=200)
        plt.close(fig)
        plots.append(f1)
        #preview_html += f"<div><strong>Preview:</strong><br><img src='/result/{file_id}/{f1}' style='max-width:360px'></div>"
    except Exception as e:
        print("plot1 error", e)

    #  === Generate PLOT 2 === 
    try:
        fig = scene_distrib_plot(df_row,TITLE_DS)
        f2 = f"{file_id}_plot2.png"
        out2 = RESULT_DIR / f2
        fig.savefig(out2, bbox_inches="tight", dpi=200)
        plt.close(fig)
        plots.append(f2)
    except Exception as e:
        print("plot2 error", e)

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
