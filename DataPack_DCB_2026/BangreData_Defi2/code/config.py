"""
Parametres communs du pipeline Bangre Data (Defi 2, disparites d'acces).

Organisation attendue sur le disque :

    <dossier racine>/
        DataPack_DCB_2026/      le Data Pack officiel, tel que telecharge
        BangreData_Defi2/       ce projet
            code/               les scripts (ce fichier)
            01_collecte/ ... 05_interpretation/

Si le Data Pack est ailleurs, il suffit de modifier DATAPACK ci-dessous.
"""
from pathlib import Path

PROJET = Path(__file__).resolve().parents[1]
DATAPACK = PROJET.parent / "DataPack_DCB_2026"

D01 = PROJET / "01_collecte"
D02 = PROJET / "02_nettoyage"
D03 = PROJET / "03_transformation"
D04 = PROJET / "04_analyse"
D05 = PROJET / "05_interpretation"
FIG = D04 / "figures"

EQUIPE = "BangreData"
DEFI = "D2"


def nom(etape, role, description, ext, version=1):
    """Construit un nom de depot conforme au modele EQUIPE_ETAPE_DEFI_ROLE_description_vN."""
    etapes = {1: "01-collecte", 2: "02-nettoyage", 3: "03-transformation",
              4: "04-analyse", 5: "05-interpretation"}
    return f"{EQUIPE}_{etapes[etape]}_{DEFI}_{role}_{description}_v{version}.{ext}"


# Fichier principal fourni dans l'espace challenge (copie brute deposee en 01).
DGESS_XLSX = D01 / nom(1, "engineer", "DGESS-prescolaire-primaire-2016-2025-brut", "xlsx")

# Sources du Data Pack utilisees (chemins relatifs au Data Pack)
SRC = {
    "annuaire_2023_24": "data/01_Education_MENAPLN_DGESS/CNS_DGESS/Annuaires/"
                        "CNS529_Annuaire_statistique_de_lenseignement_primaire_2023_2024.csv",
    "annuaire_2024_25": "data/01_Education_MENAPLN_DGESS/CNS_DGESS/Annuaires/"
                        "CNS530_Annuaire_statistique_de_lenseignement_primaire_2024_2025.csv",
    "esu_dec2022": "data/01_Education_MENAPLN_DGESS/ESU_Rapports_mensuels/"
                   "RAPPORT_STATISTIQUE_MENSUEL_ESU_DECEMBRE_2022.csv",
    "pdi_dec2022": "03_Conditions_de_Vie_et_Emploi/PDI_CONASUR/"
                   "situation-des-pdi-par-communes-accueil-du-31-decembre-2022-1.xlsx",
    "limites_geojson": "04_Cartographie_SIG/COD-AB_limites_administratives/"
                       "bfa_admin_boundaries.geojson.zip",
}

# Les 13 regions de la nomenclature DGESS (ancien decoupage), avec leur P-code COD-AB "old".
REGIONS = {
    "BF46": "Boucle du Mouhoun", "BF47": "Cascades", "BF13": "Centre",
    "BF48": "Centre-Est", "BF49": "Centre-Nord", "BF50": "Centre-Ouest",
    "BF51": "Centre-Sud", "BF52": "Est", "BF53": "Hauts-Bassins",
    "BF54": "Nord", "BF55": "Plateau-Central", "BF56": "Sahel", "BF57": "Sud-Ouest",
}

ANNEES = list(range(2016, 2026))  # annee de fin de l'annee scolaire : 2016 = 2015-2016


def annee_scolaire(fin):
    return f"{fin - 1}-{fin}"
