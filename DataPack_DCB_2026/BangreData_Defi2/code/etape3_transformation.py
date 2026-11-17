"""
Etape 3 : transformation.

On passe des tables propres (format long) au modele d'analyse :

  * table REGION x ANNEE (13 regions + national, 2016 a 2025) avec tous les
    indicateurs par sexe, les ecarts filles-garcons et des variables derivees
    (population scolarisable implicite, enfants non scolarises estimes,
    perte d'effectif depuis le pic, contexte de crise) ;
  * table PROVINCE x ANNEE (45 provinces, 2023-2024 et 2024-2025) pour l'ecart
    urbain-rural et la part des filles selon le milieu ;
  * fond de carte des 13 regions et 45 provinces (ancien decoupage) obtenu en
    regroupant les polygones COD-AB par leur P-code "old".
"""
import json
import zipfile

import numpy as np
import pandas as pd
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from config import D01, D02, D03, REGIONS, nom

rd = lambda f: pd.read_csv(D02 / f, sep=";", encoding="utf-8-sig")


def table_regions():
    prim = rd(nom(2, "engineer", "primaire-indicateurs-region-annee-sexe", "csv"))
    pres = rd(nom(2, "engineer", "prescolaire-indicateurs-region-annee-sexe", "csv"))
    ecoles = rd(nom(2, "engineer", "primaire-ecoles-region-statut", "csv"))
    x = pd.concat([prim, pres])
    x["var"] = np.where(x.sexe == "IPS", x.indicateur, x.indicateur + "_" + x.sexe)
    t = x.pivot_table(index=["region_code", "region", "annee_fin", "annee_scolaire"], columns="var",
                      values="valeur").reset_index()
    t.columns.name = None
    t = t.rename(columns={c: c.replace("nouveaux_inscrits_cp1", "cp1").replace("taux_reussite_cep", "cep")
                          .replace("effectif_prescolaire", "eff_presco").replace("tbs_prescolaire", "tbs_presco")
                          .replace("ips_tbs_prescolaire", "ips_tbs_presco").replace("effectif", "eff")
                          for c in t.columns})
    e = ecoles.pivot_table(index=["region_code", "annee_fin"], columns="statut", values="nb_ecoles").reset_index()
    e = e.rename(columns={"Public": "ecoles_public", "Prive": "ecoles_prive", "Total": "ecoles_total"})
    t = t.merge(e, on=["region_code", "annee_fin"], how="left")

    # Parite et ecarts
    t["part_filles"] = 100 * t.eff_F / t.eff_T
    t["ecart_tbs_pts"] = t.tbs_F - t.tbs_G
    t["ecart_tap_pts"] = t.tap_F - t.tap_G
    t["ecart_cep_pts"] = t.cep_F - t.cep_G
    t["ips_cp1"] = t.cp1_F / t.cp1_G
    # Population scolarisable implicite (6-11 ans) : effectif / TBS. C'est la population
    # que la DGESS a utilisee au denominateur ; on la retrouve sans hypothese externe.
    for s in ("G", "F", "T"):
        t[f"pop611_{s}"] = t[f"eff_{s}"] / (t[f"tbs_{s}"] / 100)
        # Enfants non scolarises : borne basse, car le TBS compte aussi les eleves hors age.
        t[f"hors_ecole_{s}"] = (t[f"pop611_{s}"] - t[f"eff_{s}"]).clip(lower=0)
    t["eleves_par_ecole"] = t.eff_T / t.ecoles_total
    t["part_prive_ecoles"] = 100 * t.ecoles_prive / t.ecoles_total

    # Dynamique : pic d'effectif de la region et perte au point bas
    t = t.sort_values(["region_code", "annee_fin"])
    t["eff_pic_avant"] = t.groupby("region_code").eff_T.cummax()
    t["perte_depuis_pic_pct"] = 100 * (t.eff_T / t.eff_pic_avant - 1)
    t["var_annuelle_eff_pct"] = 100 * t.groupby("region_code").eff_T.pct_change()
    t["var_annuelle_eff_F_pct"] = 100 * t.groupby("region_code").eff_F.pct_change()
    t["var_annuelle_eff_G_pct"] = 100 * t.groupby("region_code").eff_G.pct_change()

    # Contexte de crise (situation au 31/12/2022)
    esu = pd.read_csv(D01 / nom(1, "engineer", "ESU-etablissements-fermes-par-region-dec2022", "csv"), sep=";", encoding="utf-8-sig")
    pdi = pd.read_csv(D01 / nom(1, "engineer", "PDI-CONASUR-par-region-dec2022", "csv"), sep=";", encoding="utf-8-sig")
    inv = {v: k for k, v in REGIONS.items()}
    esu["region_code"] = esu.region.map(inv)
    pdi["region_code"] = pdi.region.str.replace("Plateau Central", "Plateau-Central").map(inv).fillna("BF")
    ctx = esu[["region_code", "etablissements_fermes", "eleves_affectes", "enseignants_affectes"]].merge(
        pdi[["region_code", "pdi_total"]], on="region_code", how="outer")
    nat = ctx[ctx.region_code != "BF"].drop(columns="region_code").sum()
    ctx = pd.concat([ctx[ctx.region_code != "BF"], pd.DataFrame([{"region_code": "BF", **nat.to_dict()}])])
    ref = t[t.annee_fin == 2023][["region_code", "ecoles_total", "pop611_T"]]
    ctx = ctx.merge(ref, on="region_code")
    ctx["pdi_pour_100_enfants_611"] = 100 * ctx.pdi_total / ctx.pop611_T
    ctx = ctx.drop(columns=["ecoles_total", "pop611_T"])
    t = t.merge(ctx, on="region_code", how="left")
    return t


def table_provinces():
    ur = rd(nom(2, "engineer", "primaire-urbain-rural-provinces-2024-2025", "csv"))
    ur["urbain_garcons"] = ur.urbain_total - ur.urbain_filles
    ur["rural_garcons"] = ur.rural_total - ur.rural_filles
    ur["part_urbain_pct"] = 100 * ur.urbain_total / ur.ensemble_total
    ur["ips_effectif_urbain"] = ur.urbain_filles / ur.urbain_garcons
    ur["ips_effectif_rural"] = ur.rural_filles / ur.rural_garcons
    ur["ips_effectif_ensemble"] = ur.ensemble_filles / (ur.ensemble_total - ur.ensemble_filles)
    ur["ecart_filles_urbain_rural_pts"] = ur.urbain_pct_filles - ur.rural_pct_filles
    ur = ur.sort_values(["niveau", "province", "region_code", "annee_fin"])
    ur["var_rural_pct"] = 100 * ur.groupby(["niveau", "region_code", "province"], dropna=False).rural_total.pct_change()
    ur["var_urbain_pct"] = 100 * ur.groupby(["niveau", "region_code", "province"], dropna=False).urbain_total.pct_change()
    return ur


def fonds_de_carte():
    """Regroupe les 47 provinces COD-AB (nouveau decoupage) en 45 provinces et 13 regions (ancien)."""
    arch = D01 / nom(1, "engineer", "COD-AB-limites-administratives-geojson", "zip")
    with zipfile.ZipFile(arch) as z:
        g = json.loads(z.read("bfa_admin2.geojson"))
    par_prov = {}
    for f in g["features"]:
        p = f["properties"]
        par_prov.setdefault((p["adm2_pcode_old"], p["adm2_name_old"]), []).append(shape(f["geometry"]))
    provinces = []
    for (code, nm), geoms in sorted(par_prov.items()):
        geom = unary_union(geoms).buffer(0)
        provinces.append({"code": code, "nom": nm, "region_code": code[:4], "geom": geom})
    regions = []
    for rc, rn in REGIONS.items():
        geom = unary_union([p["geom"] for p in provinces if p["region_code"] == rc]).buffer(0)
        regions.append({"code": rc, "nom": rn, "region_code": rc, "geom": geom})

    def ecrire(objets, fichier, tol):
        feats = [{"type": "Feature", "properties": {k: v for k, v in o.items() if k != "geom"},
                  "geometry": mapping(o["geom"].simplify(tol, preserve_topology=True))} for o in objets]
        fc = {"type": "FeatureCollection", "features": feats}
        txt = json.dumps(fc, ensure_ascii=False)
        # 4 decimales de degre (environ 10 m) suffisent pour une carte a l'echelle du pays
        import re
        txt = re.sub(r"(-?\d+\.\d{4})\d+", r"\1", txt)
        (D03 / fichier).write_text(txt, encoding="utf-8")
        return len(feats)

    n1 = ecrire(regions, nom(3, "architect", "fond-de-carte-13-regions-ancien-decoupage", "geojson"), 0.01)
    n2 = ecrire(provinces, nom(3, "architect", "fond-de-carte-45-provinces-ancien-decoupage", "geojson"), 0.008)
    corr = pd.DataFrame([{"province_pcode_old": p["code"], "province": p["nom"], "region_pcode_old": p["region_code"],
                          "region": REGIONS[p["region_code"]]} for p in provinces])
    nouv = pd.DataFrame([{"province_pcode_old": f["properties"]["adm2_pcode_old"], "province_pcode_2025": f["properties"]["adm2_pcode"],
                          "province_2025": f["properties"]["adm2_name1"], "region_pcode_2025": f["properties"]["adm1_pcode"],
                          "region_2025": f["properties"]["adm1_name1"]} for f in g["features"]])
    corr = corr.merge(nouv, on="province_pcode_old")
    corr.to_csv(D03 / nom(3, "architect", "table-de-correspondance-ancien-nouveau-decoupage", "csv"), index=False, sep=";", encoding="utf-8-sig")
    return n1, n2, len(corr)


DICTIONNAIRE = [
    # variable, definition, unite, source / regle de calcul
    ("region_code", "P-code de la region (ancien decoupage, 13 regions) ; BF = ensemble du pays", "code", "COD-AB adm1_pcode_old"),
    ("annee_fin", "Annee civile de fin de l'annee scolaire (2016 = 2015-2016)", "annee", "convention equipe"),
    ("eff_G / eff_F / eff_T", "Effectif d'eleves du primaire, garcons / filles / total", "eleves", "DGESS tableau 1"),
    ("cp1_G / cp1_F / cp1_T", "Nouveaux inscrits au CP1", "eleves", "DGESS tableau 5"),
    ("tba_*", "Taux brut d'admission au CP1 = nouveaux inscrits / population de 6 ans", "%", "DGESS tableau 6"),
    ("tbs_*", "Taux brut de scolarisation au primaire = effectif / population de 6-11 ans", "%", "DGESS tableau 7"),
    ("tap_*", "Taux d'achevement du primaire", "%", "DGESS tableau 8"),
    ("cep_*", "Taux de reussite au CEP (session de fin d'annee)", "%", "DGESS tableau 9"),
    ("ips_tba / ips_tbs / ips_tap", "Indice de parite filles/garcons du taux (1 = parite ; < 1 filles en retard ; > 1 garcons en retard)", "ratio", "DGESS tableaux 10 a 12"),
    ("ips_cp1", "Nouvelles inscrites / nouveaux inscrits au CP1", "ratio", "calcul : cp1_F / cp1_G"),
    ("part_filles", "Part des filles dans l'effectif", "%", "calcul : 100 x eff_F / eff_T"),
    ("ecart_tbs_pts / ecart_tap_pts / ecart_cep_pts", "Ecart filles moins garcons", "points de %", "calcul : taux_F - taux_G"),
    ("pop611_*", "Population de 6-11 ans implicite dans le TBS publie", "enfants", "calcul : eff / (tbs / 100)"),
    ("hors_ecole_*", "Enfants de 6-11 ans non scolarises, estimation basse", "enfants", "calcul : max(pop611 - eff ; 0) ; borne basse car le TBS inclut les eleves hors age"),
    ("eff_presco_* / tbs_presco_* / ips_tbs_presco", "Effectif, TBS et IPS du prescolaire", "eleves / % / ratio", "DGESS prescolaire tableaux 1, 5, 6"),
    ("ecoles_public / ecoles_prive / ecoles_total", "Nombre d'ecoles primaires", "ecoles", "DGESS tableau 13"),
    ("eleves_par_ecole", "Effectif moyen par ecole", "eleves", "calcul : eff_T / ecoles_total"),
    ("perte_depuis_pic_pct", "Ecart de l'effectif de l'annee a son plus haut niveau atteint depuis 2016", "%", "calcul"),
    ("var_annuelle_eff_*", "Variation de l'effectif par rapport a l'annee precedente", "%", "calcul"),
    ("etablissements_fermes", "Etablissements scolaires fermes (tous ordres) au 31/12/2022", "etablissements", "ST-ESU decembre 2022"),
    ("eleves_affectes", "Eleves affectes par les fermetures (tous ordres) au 31/12/2022", "eleves", "ST-ESU decembre 2022"),
    ("pdi_total", "Personnes deplacees internes enregistrees dans la region d'accueil au 31/12/2022", "personnes", "CONASUR"),
    ("pdi_pour_100_enfants_611", "PDI rapportees a la population 6-11 ans implicite 2022-2023 (indicateur de pression)", "ratio", "calcul"),
    ("part_urbain_pct (provinces)", "Part des eleves scolarises en milieu urbain", "%", "annuaires CNS529, CNS530 tableau I.2"),
    ("ips_effectif_urbain / _rural", "Filles / garcons inscrits selon le milieu", "ratio", "calcul"),
    ("ecart_filles_urbain_rural_pts", "Part des filles en ville moins part des filles en milieu rural", "points de %", "calcul"),
]


if __name__ == "__main__":
    D03.mkdir(parents=True, exist_ok=True)
    t = table_regions()
    t.to_csv(D03 / nom(3, "engineer", "table-indicateurs-region-annee", "csv"), index=False, sep=";", encoding="utf-8-sig", float_format="%.4f")
    print(f"[03] table region x annee : {t.shape}")
    p = table_provinces()
    p.to_csv(D03 / nom(3, "engineer", "table-urbain-rural-provinces-2024-2025", "csv"), index=False, sep=";", encoding="utf-8-sig", float_format="%.4f")
    print(f"[03] table provinces : {p.shape}")
    print("[03] fonds de carte (regions, provinces, correspondances) :", fonds_de_carte())
    pd.DataFrame(DICTIONNAIRE, columns=["variable", "definition", "unite", "source_ou_regle"]).to_csv(
        D03 / nom(3, "architect", "dictionnaire-des-variables", "csv"), index=False, sep=";", encoding="utf-8-sig")
