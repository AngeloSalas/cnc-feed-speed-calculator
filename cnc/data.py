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
