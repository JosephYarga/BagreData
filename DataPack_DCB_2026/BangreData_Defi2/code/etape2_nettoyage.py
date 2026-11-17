"""
Etape 2 : nettoyage.

Le fichier DGESS est un classeur de presentation : titres, cellules fusionnees,
regions ecrites en titre de bloc, lignes de total, libelles d'annee ecrits de
quatre facons differentes. On le remet en format long, une valeur par ligne :

    region_code | region | annee_fin | annee_scolaire | sexe | indicateur | valeur

Chaque correction est tracee dans le journal de nettoyage, et les totaux sont
controles (somme des regions = national, G + F = T, IPS recalcule, recoupement
avec les annuaires).
"""
import re

import numpy as np
import openpyxl
import pandas as pd

from config import D01, D02, DGESS_XLSX, REGIONS, annee_scolaire, nom

JOURNAL = []


def log(etape, objet, action, n=None):
    JOURNAL.append({"n": len(JOURNAL) + 1, "etape": etape, "objet": objet, "action": action,
                    "lignes_concernees": n})


# ----------------------------------------------------------------------------
# Referentiels de libelles
# ----------------------------------------------------------------------------
NOM_VERS_CODE = {v.upper().replace("-", " "): k for k, v in REGIONS.items()}
VARIANTES = {"HAUT BASSINS": "BF53", "PLATEAU CENTRA": "BF53x", "PLATEAU CENTRAL": "BF55",
             "BURKINA FASO": "BF", "NATIONAL": "BF", "TOTAL GENERAL": "BF", "TOTAL GÉNÉRAL": "BF"}


def code_region(libelle):
    """Ramene un libelle de region (toutes graphies rencontrees) a son P-code."""
    if libelle is None:
        return None
    s = str(libelle).strip().upper().replace("-", " ").replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^TOTAL ", "", s) if s.startswith("TOTAL ") and s not in ("TOTAL GENERAL", "TOTAL GÉNÉRAL") else s
    if s in NOM_VERS_CODE:
        return NOM_VERS_CODE[s]
    if s in VARIANTES:
        return VARIANTES[s] if VARIANTES[s] != "BF53x" else "BF55"
    if s.startswith("PLATEAU"):
        return "BF55"
    return None


SEXE = {"G": "G", "GARCONS": "G", "GARÇONS": "G", "F": "F", "FILLES": "F", "T": "T", "TOTAL": "T"}


def annee_fin(valeur):
    """'2015-2016', '2015/16', '2015/2016', '2015-16', 2016 ou '2024/25' -> 2016 ... 2025."""
    if valeur is None:
        return None
    s = str(valeur).split("\n")[0].strip()  # certaines cellules d'en-tete portent un texte parasite apres l'annee
    m = re.match(r"^(\d{4})\s*[-/]\s*(\d{2,4})$", s)
    if m:
        return int(m.group(1)) + 1
    m = re.match(r"^(\d{4})(?:\.0)?$", s)
    if m:
        return int(m.group(1))
    return None


def propre(v):
    """Ecarte les textes non statistiques glisses dans les cellules (notes, commentaires)."""
    if isinstance(v, str) and len(v) > 250:
        tete = v.split("\n")[0].strip()
        return tete if annee_fin(tete) else None
    return v


def charger_feuille(wb, nomf):
    ws = wb[nomf]
    grille = [[propre(c) for c in r] for r in ws.iter_rows(values_only=True)]
    n_parasites = sum(1 for r in ws.iter_rows(values_only=True) for c in r if isinstance(c, str) and len(c) > 250)
    if n_parasites:
        log("lecture", nomf, "cellules de texte non statistique (hors tableau ou collees a un en-tete) ignorees", n_parasites)
    return grille


# ----------------------------------------------------------------------------
# Lecteurs selon la mise en page
# ----------------------------------------------------------------------------
def lire_blocs_sexe(grille, ligne_entete, col_lib=0, col_sexe=1, col_annees=2, stop_national=True):
    """Tableaux 'REGION | SEXE | 2015-2016 ...' ou la region n'est ecrite que sur la 1re ligne du bloc."""
    entete = grille[ligne_entete]
    annees = {j: annee_fin(entete[j]) for j in range(col_annees, len(entete)) if annee_fin(entete[j])}
    out, courant = [], None
    for r in grille[ligne_entete + 1:]:
        if r[col_lib] is not None:
            courant = r[col_lib]
        sexe = SEXE.get(str(r[col_sexe]).strip().upper()) if r[col_sexe] is not None else None
        if courant is None or sexe is None:
            if all(v is None for v in r[:col_annees + 3]) and out:
                break
            continue
        for j, a in annees.items():
            if r[j] is not None:
                out.append((str(courant).strip(), a, sexe, float(r[j])))
    return pd.DataFrame(out, columns=["libelle", "annee_fin", "sexe", "valeur"])


def lire_triplets(grille, ligne_entete):
    """Tableaux ou chaque annee occupe trois colonnes G | F | T."""
    entete, sous = grille[ligne_entete], grille[ligne_entete + 1]
    cols, annee = {}, None
    for j in range(1, len(entete)):
        if annee_fin(entete[j]):
            annee = annee_fin(entete[j])
        if annee and sous[j] in ("G", "F", "T"):
            cols[j] = (annee, sous[j])
    out = []
    for r in grille[ligne_entete + 2:]:
        if r[0] is None:
            if out:
                break
            continue
        for j, (a, s) in cols.items():
            if r[j] is not None:
                out.append((str(r[0]).strip(), a, s, float(r[j])))
    return pd.DataFrame(out, columns=["libelle", "annee_fin", "sexe", "valeur"])


def lire_simple(grille, ligne_entete):
    """Tableaux 'Regions | 2015-16 | 2016-17 ...' (une valeur par region et par annee)."""
    entete = grille[ligne_entete]
    annees = {j: annee_fin(entete[j]) for j in range(1, len(entete)) if annee_fin(entete[j])}
    out = []
    for r in grille[ligne_entete + 1:]:
        if r[0] is None:
            if out:
                break
            continue
        for j, a in annees.items():
            if r[j] is not None:
                out.append((str(r[0]).strip(), a, float(r[j])))
    return pd.DataFrame(out, columns=["libelle", "annee_fin", "valeur"])


def lire_blocs_statut(grille, ligne_entete):
    """Tableaux 'REGION | STATUT | annees' avec ligne 'Total <region>' (ecoles, structures, salles)."""
    entete = grille[ligne_entete]
    annees = {j: annee_fin(entete[j]) for j in range(2, len(entete)) if annee_fin(entete[j])}
    out, courant = [], None
    for r in grille[ligne_entete + 1:]:
        a, b = r[0], r[1]
        if a is None and b is None:
            if out:
                break
            continue
        if a is not None and str(a).strip().lower().startswith("total"):
            statut, lib = "Total", (courant if str(a).strip().lower() != "total général" else "Total général")
            if b is not None:
                statut, lib = str(b).strip(), courant
        else:
            if a is not None:
                courant = str(a).strip()
            statut, lib = str(b).strip(), courant
        for j, an in annees.items():
            if r[j] is not None:
                out.append((lib, statut, an, float(r[j])))
    df = pd.DataFrame(out, columns=["libelle", "statut", "annee_fin", "valeur"])
    df["statut"] = df.statut.replace({"Privé": "Prive", "PRIVE": "Prive", "Total": "Total"})
    return df


def trouver(grille, premiere_cellule, apres=0):
    for i, r in enumerate(grille):
        if i >= apres and r[0] is not None and str(r[0]).strip().upper().startswith(premiere_cellule.upper()):
            return i
    raise ValueError(premiere_cellule)


def coder(df, objet):
    df = df.copy()
    df["region_code"] = df.libelle.map(code_region)
    inconnus = df[df.region_code.isna()].libelle.unique()
    if len(inconnus):
        raise ValueError(f"{objet} : libelles non reconnus {inconnus}")
    variantes = sorted(set(l for l in df.libelle.unique()
                           if l.upper().replace("-", " ") not in NOM_VERS_CODE and code_region(l) != "BF"))
    if variantes:
        log("harmonisation", objet, "libelles de region harmonises : " + ", ".join(variantes),
            int(df.libelle.isin(variantes).sum()))
    df["region"] = df.region_code.map(REGIONS).fillna("Burkina Faso")
    df["annee_scolaire"] = df.annee_fin.map(annee_scolaire)
    return df.drop(columns="libelle")


# ----------------------------------------------------------------------------
# Construction des tables propres
# ----------------------------------------------------------------------------
def tables_primaire(wb):
    morceaux = []
    g = charger_feuille(wb, "Feuil1")
    d = coder(lire_blocs_sexe(g, trouver(g, "REGION")), "Feuil1 effectifs"); d["indicateur"] = "effectif"; morceaux.append(d)
    g = charger_feuille(wb, "Feuil5")
    d = coder(lire_blocs_sexe(g, trouver(g, "REGION")), "Feuil5 nouveaux inscrits CP1"); d["indicateur"] = "nouveaux_inscrits_cp1"; morceaux.append(d)
    for f, ind in (("Feuil6", "tba"), ("Feuil7", "tbs"), ("Feuil8", "tap")):
        g = charger_feuille(wb, f)
        d = coder(lire_triplets(g, trouver(g, "Régions")), f"{f} {ind}"); d["indicateur"] = ind; morceaux.append(d)
    g = charger_feuille(wb, "Feuil9")
    d = coder(lire_blocs_sexe(g, trouver(g, "Région")), "Feuil9 CEP"); d["indicateur"] = "taux_reussite_cep"; morceaux.append(d)
    log("convention", "Feuil9 CEP", "annee de session du CEP (2016...2025) rattachee a l'annee scolaire qui se termine (2015-2016...2024-2025)")
    for f, ind in (("Feuil10", "ips_tba"), ("Feuil11", "ips_tbs"), ("Feuil12", "ips_tap")):
        g = charger_feuille(wb, f)
        d = coder(lire_simple(g, trouver(g, "Régions")), f"{f} {ind}"); d["sexe"] = "IPS"; d["indicateur"] = ind; morceaux.append(d)
    df = pd.concat(morceaux, ignore_index=True)
    taux = df.indicateur.isin(["tba", "tbs", "tap", "taux_reussite_cep"])
    df.loc[taux, "valeur"] = df.loc[taux, "valeur"].round(2)
    df.loc[df.indicateur.str.startswith("ips"), "valeur"] = df.loc[df.indicateur.str.startswith("ips"), "valeur"].round(4)
    log("format", "taux et IPS", "taux arrondis a 2 decimales, IPS a 4 decimales (precision heterogene dans la source)", int(taux.sum()))
    return df[["region_code", "region", "annee_fin", "annee_scolaire", "sexe", "indicateur", "valeur"]]


def tables_nationales(wb):
    g = charger_feuille(wb, "Feuil3")
    m = lire_blocs_sexe(g, trouver(g, "MILIEU")).rename(columns={"libelle": "milieu"})
    m["milieu"] = m.milieu.str.capitalize().replace({"National": "Ensemble"})
    m["annee_scolaire"] = m.annee_fin.map(annee_scolaire)
    g = charger_feuille(wb, "Feuil4")
    i = trouver(g, "STATUT")
    entete = g[i]
    annees = {j: annee_fin(entete[j]) for j in range(3, len(entete)) if annee_fin(entete[j])}
    out, statut, niveau = [], None, None
    for r in g[i + 1:]:
        if all(v is None for v in r[:6]):
            if out:
                break
            continue
        if r[0] is not None:
            statut = str(r[0]).strip()
        if r[1] is not None:
            niveau = str(r[1]).strip()
        s = SEXE.get(str(r[2]).strip().upper()) if r[2] else None
        if not s or statut.upper().startswith("TOTAL") and niveau is None:
            continue
        for j, a in annees.items():
            if r[j] is not None:
                out.append((statut, niveau, a, s, float(r[j])))
    n = pd.DataFrame(out, columns=["statut", "niveau", "annee_fin", "sexe", "effectif"])
    n = n[n.niveau.isin(["CP1", "CP2", "CE1", "CE2", "CM1", "CM2"]) & ~n.statut.str.upper().str.startswith("TOTAL")]
    n["statut"] = n.statut.replace({"PRIVE": "Prive", "Public": "Public"})
    n = n.groupby(["niveau", "annee_fin", "sexe"], as_index=False).effectif.sum()
    n["annee_scolaire"] = n.annee_fin.map(annee_scolaire)
    log("agregation", "Feuil4 niveaux", "public + prive additionnes par niveau (CP1 a CM2) pour obtenir l'ensemble national", len(n))
    return m, n


def tables_prescolaire(wb):
    g = charger_feuille(wb, "PRESCOLAIRE")
    t1 = trouver(g, "REGION")
    eff = coder(lire_triplets(g, t1), "PRESCOLAIRE T1"); eff["indicateur"] = "effectif_prescolaire"
    t5 = trouver(g, "Tableau 5")
    tbs = coder(lire_triplets(g, t5 + 1), "PRESCOLAIRE T5"); tbs["indicateur"] = "tbs_prescolaire"
    t6 = trouver(g, "Tableau 6")
    ips = coder(lire_simple(g, t6 + 1), "PRESCOLAIRE T6"); ips["sexe"] = "IPS"; ips["indicateur"] = "ips_tbs_prescolaire"
    df = pd.concat([eff, tbs, ips], ignore_index=True)
    return df[["region_code", "region", "annee_fin", "annee_scolaire", "sexe", "indicateur", "valeur"]]


def table_ecoles(wb):
    g = charger_feuille(wb, "Feuil13")
    i = trouver(g, "REGION")
    entete = g[i]
    annees = {j: annee_fin(entete[j]) for j in range(2, len(entete)) if annee_fin(entete[j])}
    out, courant = [], None
    for r in g[i + 1:]:
        if r[1] is None:
            if out:
                break
            continue
        if r[0] is not None:
            courant = r[0]
        for j, a in annees.items():
            if r[j] is not None:
                out.append((str(courant).strip(), str(r[1]).strip().replace("Privé", "Prive"), a, float(r[j])))
    d = coder(pd.DataFrame(out, columns=["libelle", "statut", "annee_fin", "valeur"]), "Feuil13 ecoles")
    return d.rename(columns={"valeur": "nb_ecoles"})[["region_code", "region", "annee_fin", "annee_scolaire", "statut", "nb_ecoles"]]


def table_urbain_rural():
    """Remet en forme l'extrait brut du tableau I.2 : une ligne par province, annee et milieu."""
    brut = pd.read_csv(D01 / nom(1, "engineer", "annuaires-CNS529-CNS530-tableau-I2-urbain-rural-extrait-brut", "csv"),
                       sep=";", dtype=str, encoding="utf-8-sig").fillna("")
    num = lambda s: float(s.replace(" ", "").replace(" ", "").replace(",", "."))
    out, region = [], None
    for _, r in brut.iterrows():
        n = int(r.nb_cellules)
        if n == 1 and code_region(r.c1) and code_region(r.c1) != "BF":
            region = code_region(r.c1)
        elif n == 10 and region:
            prov = r.c1.strip()
            vals = [num(r[f"c{k}"]) for k in range(2, 11)]
            out.append((r.annee_scolaire, region, prov, *vals))
    cols = ["annee_scolaire", "region_code", "province", "urbain_total", "urbain_filles", "urbain_pct_filles",
            "rural_total", "rural_filles", "rural_pct_filles", "ensemble_total", "ensemble_filles", "ensemble_pct_filles"]
    df = pd.DataFrame(out, columns=cols)
    df["niveau"] = np.where(df.province.str.lower().str.startswith("total"), "region", "province")
    df.loc[df.niveau == "region", "province"] = None
    df["region"] = df.region_code.map(REGIONS)
    df["annee_fin"] = df.annee_scolaire.str[-4:].astype(int)
    log("restructuration", "tableau I.2 annuaires", "lignes PDF regroupees par bloc de region (titre de bloc reporte sur les provinces, y compris l'Est coupe entre les pages 17 et 18)", len(df))
    log("format", "tableau I.2 annuaires", "separateurs de milliers (espace) et decimales a la virgule convertis en nombres", len(df))
    noms = {"COMOE": "Comoé", "LERABA": "Léraba", "KOULPELOGO": "Koulpélogo", "BOULKIEMDE": "Boulkiemdé",
            "SANGUIE": "Sanguié", "BAZEGA": "Bazèga", "ZOUNDWEOGO": "Zoundwéogo", "KOMONDJARI": "Komandjari",
            "KENEDOUGOU": "Kénédougou", "PASSORE": "Passoré", "KOURWEOGO": "Kourwéogo", "SENO": "Séno",
            "LES BALE": "Balé", "BALE": "Balé"}
    pv = df.niveau == "province"
    df.loc[pv, "province"] = df.loc[pv, "province"].map(lambda p: noms.get(p.upper(), p.title()))
    log("harmonisation", "provinces", "noms de provinces alignes sur la graphie COD-AB (accents, 'LES BALE' -> 'Balé', 'KOMONDJARI' -> 'Komandjari')", int(pv.sum()))
    return df[["annee_fin", "annee_scolaire", "niveau", "region_code", "region", "province"] + cols[3:]]


# ----------------------------------------------------------------------------
# Controles
# ----------------------------------------------------------------------------
def controles(prim, pres, ecoles, milieu, ur):
    c = []

    def ajoute(test, objet, ecart_max, n):
        c.append({"controle": test, "objet": objet, "ecart_absolu_max": round(float(ecart_max), 4),
                  "observations": int(n), "resultat": "OK" if ecart_max < 0.5 else "ECART"})

    for ind, d in (("effectif", prim), ("nouveaux_inscrits_cp1", prim), ("effectif_prescolaire", pres)):
        x = d[d.indicateur == ind]
        reg = x[x.region_code != "BF"].groupby(["annee_fin", "sexe"]).valeur.sum()
        nat = x[x.region_code == "BF"].set_index(["annee_fin", "sexe"]).valeur
        ajoute("somme des 13 regions = ligne nationale", ind, (reg - nat).abs().max(), len(reg))
        p = x.pivot_table(index=["region_code", "annee_fin"], columns="sexe", values="valeur")
        ajoute("G + F = T", ind, (p["G"] + p["F"] - p["T"]).abs().max(), len(p))
    e = ecoles.pivot_table(index=["region_code", "annee_fin"], columns="statut", values="nb_ecoles")
    ajoute("Public + Prive = Total", "ecoles primaires", (e.Public + e.Prive - e.Total).abs().max(), len(e))
    er = ecoles[(ecoles.region_code != "BF") & (ecoles.statut == "Total")].groupby("annee_fin").nb_ecoles.sum()
    en = ecoles[(ecoles.region_code == "BF") & (ecoles.statut == "Total")].set_index("annee_fin").nb_ecoles
    ajoute("somme des 13 regions = ligne nationale", "ecoles primaires", (er - en).abs().max(), len(er))
    mm = milieu.pivot_table(index=["annee_fin", "sexe"], columns="milieu", values="valeur")
    ajoute("Urbain + Rural = Ensemble", "effectifs par milieu", (mm.Urbain + mm.Rural - mm.Ensemble).abs().max(), len(mm))
    nat_eff = prim[(prim.indicateur == "effectif") & (prim.region_code == "BF")].set_index(["annee_fin", "sexe"]).valeur
    ajoute("total par milieu = total par region", "effectifs nationaux", (mm.Ensemble - nat_eff).abs().max(), len(mm))
    # IPS publie vs IPS recalcule a partir des taux par sexe
    for ind in ("tba", "tbs", "tap"):
        t = prim[prim.indicateur == ind].pivot_table(index=["region_code", "annee_fin"], columns="sexe", values="valeur")
        ips = prim[prim.indicateur == f"ips_{ind}"].set_index(["region_code", "annee_fin"]).valeur
        ecart = (t.F / t.G - ips).abs()
        c.append({"controle": "IPS publie = taux filles / taux garcons", "objet": f"ips_{ind}",
                  "ecart_absolu_max": round(float(ecart.max()), 4), "observations": int(ecart.notna().sum()),
                  "resultat": "OK" if ecart.max() < 0.01 else "ECART (voir journal)"})
    # Recoupement fichier principal / annuaires (effectifs regionaux par sexe)
    reg_ur = ur[ur.niveau == "region"].set_index(["region_code", "annee_fin"])
    x = prim[(prim.indicateur == "effectif") & (prim.region_code != "BF")].pivot_table(
        index=["region_code", "annee_fin"], columns="sexe", values="valeur")
    j = reg_ur.join(x, how="inner")
    ajoute("effectif region (fichier DGESS) = Total Region (annuaire)", "effectif total 2024 et 2025", (j.ensemble_total - j["T"]).abs().max(), len(j))
    ajoute("effectif region (fichier DGESS) = Total Region (annuaire)", "effectif filles 2024 et 2025", (j.ensemble_filles - j["F"]).abs().max(), len(j))
    pv = ur[ur.niveau == "province"].groupby(["region_code", "annee_fin"])[["urbain_total", "rural_total", "ensemble_total"]].sum()
    ajoute("somme des provinces = Total Region", "annuaires tableau I.2", (pv - reg_ur[["urbain_total", "rural_total", "ensemble_total"]]).abs().max().max(), len(pv))
    pv2 = ur[ur.niveau == "province"]
    ajoute("urbain + rural = ensemble", "provinces tableau I.2", (pv2.urbain_total + pv2.rural_total - pv2.ensemble_total).abs().max(), len(pv2))
    # Plages plausibles
    for ind, lo, hi in (("tbs", 0, 200), ("tba", 0, 200), ("tap", 0, 200), ("taux_reussite_cep", 0, 100)):
        v = prim[prim.indicateur == ind].valeur
        hors = ((v < lo) | (v > hi)).sum()
        c.append({"controle": f"valeurs dans [{lo} ; {hi}]", "objet": ind, "ecart_absolu_max": 0,
                  "observations": int(len(v)), "resultat": "OK" if hors == 0 else f"{hors} hors plage"})
    return pd.DataFrame(c)


def ecarts_ips(prim):
    """Detaille les IPS publies qui s'ecartent du ratio recalcule (utile pour le journal)."""
    lignes = []
    for ind in ("tba", "tbs", "tap"):
        t = prim[prim.indicateur == ind].pivot_table(index=["region_code", "region", "annee_fin"], columns="sexe", values="valeur")
        ips = prim[prim.indicateur == f"ips_{ind}"].set_index(["region_code", "region", "annee_fin"]).valeur
        d = pd.DataFrame({"ips_publie": ips, "ips_recalcule": (t.F / t.G).round(4)}).dropna()
        d["ecart"] = (d.ips_publie - d.ips_recalcule).round(4)
        d = d[d.ecart.abs() >= 0.01].reset_index()
        d["indicateur"] = f"ips_{ind}"
        lignes.append(d)
    return pd.concat(lignes)


if __name__ == "__main__":
    D02.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.load_workbook(DGESS_XLSX, data_only=True)
    log("lecture", DGESS_XLSX.name, "14 feuilles lues ; titres, lignes vides et mises en forme ignores")
    prim = tables_primaire(wb)
    milieu, niveaux = tables_nationales(wb)
    pres = tables_prescolaire(wb)
    ecoles = table_ecoles(wb)
    ur = table_urbain_rural()
    log("restructuration", "fichier DGESS", "tableaux larges (annees en colonnes, sexe en sous-colonnes ou en lignes) convertis en format long", len(prim) + len(pres))
    log("separation", "lignes de total", "lignes nationales conservees avec region_code = BF pour les controles, jamais additionnees aux regions")

    sorties = {
        nom(2, "engineer", "primaire-indicateurs-region-annee-sexe", "csv"): prim,
        nom(2, "engineer", "primaire-effectifs-milieu-national", "csv"): milieu,
        nom(2, "engineer", "primaire-effectifs-niveau-sexe-national", "csv"): niveaux,
        nom(2, "engineer", "prescolaire-indicateurs-region-annee-sexe", "csv"): pres,
        nom(2, "engineer", "primaire-ecoles-region-statut", "csv"): ecoles,
        nom(2, "engineer", "primaire-urbain-rural-provinces-2024-2025", "csv"): ur,
    }
    for f, d in sorties.items():
        d.to_csv(D02 / f, index=False, sep=";", encoding="utf-8-sig")
        print(f"[02] {f} : {len(d)} lignes")

    ctrl = controles(prim, pres, ecoles, milieu, ur)
    ctrl.to_csv(D02 / nom(2, "engineer", "controle-des-totaux", "csv"), index=False, sep=";", encoding="utf-8-sig")
    ec = ecarts_ips(prim)
    if len(ec):
        ec.to_csv(D02 / nom(2, "engineer", "ips-publies-ecarts-au-recalcul", "csv"), index=False, sep=";", encoding="utf-8-sig")
        log("controle", "IPS", f"{len(ec)} IPS publies s'ecartent de plus de 0,01 du ratio filles/garcons recalcule : valeurs publiees conservees, ecarts listes a part", len(ec))
    log("harmonisation", "lignes nationales", "libelles 'NATIONAL', 'Burkina Faso' et 'Total general' ramenes a un code unique BF")
    jr = pd.DataFrame(JOURNAL)
    jr["lignes_concernees"] = jr.lignes_concernees.astype("Int64")
    jr.to_csv(D02 / nom(2, "engineer", "journal-de-nettoyage", "csv"), index=False, sep=";", encoding="utf-8-sig")
    print(ctrl.to_string(index=False))
