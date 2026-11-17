"""
Relance complete du travail, de la collecte au tableau de bord.

    cd BangreData_Defi2/code
    pip install -r requirements.txt
    python lancer_tout.py

Duree : moins d'une minute sur un ordinateur portable.
"""
import runpy
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
ETAPES = ["etape1_collecte.py", "etape2_nettoyage.py", "etape3_transformation.py",
          "etape4_analyse.py", "etape5_interpretation.py"]

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ICI))
    t0 = time.time()
    for e in ETAPES:
        print(f"\n=== {e} ===")
        runpy.run_path(str(ICI / e), run_name="__main__")
    print(f"\nTermine en {time.time() - t0:.0f} s. Ouvrir 05_interpretation/*tableau-de-bord*.html dans un navigateur.")
