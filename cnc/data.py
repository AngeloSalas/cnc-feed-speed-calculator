# cnc/data.py

# Basic starter defaults (tune to your shop/machine/rigidity/grade)
MATERIALS = {
    "Cast Iron": {"sfm_min": 600, "sfm_max": 1200},
    "4140": {"sfm_min": 250, "sfm_max": 600},
    "416 SS": {"sfm_min": 180, "sfm_max": 450},
    "316 SS": {"sfm_min": 150, "sfm_max": 350},
    "6061 Aluminum": {"sfm_min": 800, "sfm_max": 2000},
}

INSERTS = {
    "CNMG (Rough)": {"ipr_min": 0.010, "ipr_max": 0.020},
    "CNMG (Finish)": {"ipr_min": 0.004, "ipr_max": 0.010},
    "DNMG (General)": {"ipr_min": 0.006, "ipr_max": 0.014},
    "VNMG (Finish/Light)": {"ipr_min": 0.003, "ipr_max": 0.008},
}

# Milling presets (starter ranges for carbide endmills; tune to your shop)
MILL_MATERIALS = {
    "Cast Iron": {"sfm_min": 500, "sfm_max": 1200, "chip_min": 0.0020, "chip_max": 0.0060},
    "4140": {"sfm_min": 250, "sfm_max": 600, "chip_min": 0.0010, "chip_max": 0.0035},
    "416 SS": {"sfm_min": 180, "sfm_max": 450, "chip_min": 0.0008, "chip_max": 0.0030},
    "316 SS": {"sfm_min": 150, "sfm_max": 350, "chip_min": 0.0006, "chip_max": 0.0025},
    "6061 Aluminum": {"sfm_min": 800, "sfm_max": 2000, "chip_min": 0.0015, "chip_max": 0.0060},
}

# Drilling presets (starter ranges; tune for HSS vs carbide and rigidity)
DRILL_MATERIALS = {
    "Cast Iron": {"sfm_min": 60, "sfm_max": 200, "ipr_min": 0.0030, "ipr_max": 0.0120, "unit_hp": 0.35},
    "4140": {"sfm_min": 40, "sfm_max": 120, "ipr_min": 0.0020, "ipr_max": 0.0100, "unit_hp": 0.55},
    "416 SS": {"sfm_min": 30, "sfm_max": 100, "ipr_min": 0.0015, "ipr_max": 0.0080, "unit_hp": 0.65},
    "316 SS": {"sfm_min": 25, "sfm_max": 80,  "ipr_min": 0.0012, "ipr_max": 0.0060, "unit_hp": 0.70},
    "6061 Aluminum": {"sfm_min": 150, "sfm_max": 400, "ipr_min": 0.0020, "ipr_max": 0.0150, "unit_hp": 0.25},
}

# Machine capability presets (EDIT THESE to match your shop)
# hp values are approximate continuous power available for that drive.
MACHINES = {
    "Lynx 300M": {
        "type": "lathe",
        "spindle_max_rpm": 3000,      # set to your chuck-safe RPM if needed
        "spindle_hp": 20.0,           # main spindle drilling power available
        "live_tool_max_rpm": 3000,    # live tool max RPM
        "live_tool_hp": 5.0,          # live tool drilling power available (often 3–7hp)
        "has_live_tool": True,
    },
    "Puma 400": {
        "type": "lathe",
        "spindle_max_rpm": 3000,
        "spindle_hp": 30.0,
        "live_tool_max_rpm": 0,
        "live_tool_hp": 0.0,
        "has_live_tool": False,
    },
    "Toshiba BMC-800": {
        "type": "mill",
        "spindle_max_rpm": 6000,
        "spindle_hp": 20.0,
        "has_live_tool": False,
    },
}
