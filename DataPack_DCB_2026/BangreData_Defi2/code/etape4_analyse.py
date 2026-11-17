"""
Etape 4 : analyse.

Questions traitees :
  Q1. Ou les ecarts d'acces sont-ils les plus grands ?  (indice IDA, typologie)
  Q2. Quel ecart pese le plus : entre regions, entre filles et garcons, entre ville et campagne ?
  Q3. Les ecarts se resorbent-ils ou se creusent-ils depuis 2016 ?  (convergence)
  Q4. Ou en sera-t-on en 2030 si les rythmes actuels se maintiennent ?  (projection testee)

Toutes les sorties vont dans 04_analyse, les graphiques dans 04_analyse/figures.
"""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import D02, D03, D04, FIG, REGIONS, nom

# Palette commune (graphiques, tableau de bord, documentation)
BLEU, ORANGE, GRIS = "#2a78d6", "#eb6834", "#898781"
ENCRE, ENCRE2, GRILLE = "#0b0b0b", "#52514e", "#e1e0d9"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": "#c3c2b7", "axes.labelcolor": ENCRE2,
    "xtick.color": ENCRE2, "ytick.color": ENCRE2, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRILLE, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "figure.dpi": 150, "savefig.bbox": "tight", "axes.titleweight": "bold", "axes.titlesize": 10,
    "axes.titlecolor": ENCRE, "legend.frameon": False,
})

T = pd.read_csv(D03 / nom(3, "engineer", "table-indicateurs-region-annee", "csv"), sep=";", encoding="utf-8-sig")
P = pd.read_csv(D03 / nom(3, "engineer", "table-urbain-rural-provinces-2024-2025", "csv"), sep=";", encoding="utf-8-sig")
MIL = pd.read_csv(D02 / nom(2, "engineer", "primaire-effectifs-milieu-national", "csv"), sep=";", encoding="utf-8-sig")
NIV = pd.read_csv(D02 / nom(2, "engineer", "primaire-effectifs-niveau-sexe-national", "csv"), sep=";", encoding="utf-8-sig")
REG = T[T.region_code != "BF"].copy()
NAT = T[T.region_code == "BF"].set_index("annee_fin")
DERNIERE = 2025


def sauver(df, role, desc):
    df.to_csv(D04 / nom(4, role, desc, "csv"), index=False, sep=";", encoding="utf-8-sig", float_format="%.4f")


# ---------------------------------------------------------------------------
# Q3. Evolution et convergence
# ---------------------------------------------------------------------------
def tendances():
    rows = []
    for rc, d in REG.groupby("region_code"):
        d = d.set_index("annee_fin")
        r = {"region_code": rc, "region": REGIONS[rc]}
        for v in ("tbs_T", "tbs_F", "tbs_G", "ips_tbs", "ips_tap", "part_filles", "eff_T"):
            for a in (2016, 2019, 2023, 2025):
                r[f"{v}_{a}"] = d.loc[a, v]
        r["var_tbs_T_2016_2025_pts"] = d.loc[2025, "tbs_T"] - d.loc[2016, "tbs_T"]
        r["var_ips_tbs_2016_2025"] = d.loc[2025, "ips_tbs"] - d.loc[2016, "ips_tbs"]
        r["var_eff_2019_2023_pct"] = 100 * (d.loc[2023, "eff_T"] / d.loc[2019, "eff_T"] - 1)
        r["var_eff_2023_2025_pct"] = 100 * (d.loc[2025, "eff_T"] / d.loc[2023, "eff_T"] - 1)
        r["eff_2025_vs_pic_pct"] = d.loc[2025, "perte_depuis_pic_pct"]
        rows.append(r)
    df = pd.DataFrame(rows)
    sauver(df, "analyst", "tendances-par-region-2016-2025")
    return df


def convergence():
    rows = []
    for a, d in REG.groupby("annee_fin"):
        w = d.pop611_T / d.pop611_T.sum()
        part_eff, part_pop = d.eff_T / d.eff_T.sum(), w
        rows.append({
            "annee_fin": a,
            "tbs_min": d.tbs_T.min(), "tbs_max": d.tbs_T.max(), "ecart_max_min_pts": d.tbs_T.max() - d.tbs_T.min(),
            "region_tbs_min": d.loc[d.tbs_T.idxmin(), "region"],
            "coef_variation_tbs_pct": 100 * d.tbs_T.std(ddof=0) / d.tbs_T.mean(),
            # Theil : inegalite de repartition des eleves par rapport aux enfants a scolariser (0 = proportionnel)
            "theil_eleves_vs_population": float((part_eff * np.log(part_eff / part_pop)).sum()),
            "ecart_moyen_parite_tbs": float((d.ips_tbs - 1).abs().mean()),
            "regions_filles_en_retard_tbs": int((d.ips_tbs < 0.97).sum()),
            "regions_garcons_en_retard_tap": int((d.ips_tap > 1.03).sum()),
            "part_urbain_national_pct": float(MIL[(MIL.annee_fin == a) & (MIL.sexe == "T") & (MIL.milieu == "Urbain")].valeur.iloc[0]
                                              / MIL[(MIL.annee_fin == a) & (MIL.sexe == "T") & (MIL.milieu == "Ensemble")].valeur.iloc[0] * 100),
        })
    df = pd.DataFrame(rows)
    sauver(df, "analyst", "convergence-entre-regions-2016-2025")
    return df


# ---------------------------------------------------------------------------
# Q2. Quel ecart pese le plus ? (en nombre d'enfants)
# ---------------------------------------------------------------------------
def poids_des_ecarts():
    rows = []
    for a, d in REG.groupby("annee_fin"):
        # Ecart filles-garcons : filles a scolariser en plus pour atteindre le TBS des garcons de la meme region
        manque_filles = ((d.tbs_G - d.tbs_F).clip(lower=0) / 100 * d.pop611_F).sum()
        manque_garcons = ((d.tbs_F - d.tbs_G).clip(lower=0) / 100 * d.pop611_G).sum()
        # Ecart territorial : enfants a scolariser pour amener chaque region au TBS national de l'annee
        cible = NAT.loc[a, "tbs_T"]
        manque_territ = ((cible - d.tbs_T).clip(lower=0) / 100 * d.pop611_T).sum()
        # Ecart a l'acces universel (TBS 100 %), borne basse
        manque_univ = d.hors_ecole_T.sum()
        rows.append({"annee_fin": a, "filles_manquantes_parite": manque_filles, "garcons_manquants_parite": manque_garcons,
                     "enfants_manquants_rattrapage_moyenne_nationale": manque_territ,
                     "enfants_hors_ecole_estimation_basse": manque_univ})
    df = pd.DataFrame(rows)
    sauver(df, "analyst", "poids-des-ecarts-en-nombre-d-enfants")
    return df


# ---------------------------------------------------------------------------
# Q1. Indice des disparites d'acces (IDA) et typologie
# ---------------------------------------------------------------------------
DIMENSIONS = {
    "d1_deficit_acces": "Deficit d'acces : 100 - TBS (si positif)",
    "d2_retard_filles_acces": "Retard des filles a l'entree et dans le cycle : moyenne de (1 - IPS TBA) et (1 - IPS TBS), si positifs",
    "d3_retard_garcons_achevement": "Retard des garcons a l'achevement : IPS TAP - 1 (si positif)",
    "d4_ecart_urbain_rural_filles": "Ecart ville-campagne pour les filles : part des filles en ville - part en milieu rural (si positif)",
    "d5_fragilite": "Fragilite : perte d'effectif par rapport au plus haut niveau atteint depuis 2016",
}


def composantes(annee=DERNIERE):
    d = REG[REG.annee_fin == annee].set_index("region_code")
    ur = P[(P.niveau == "region") & (P.annee_fin == annee)].set_index("region_code")
    c = pd.DataFrame(index=d.index)
    c["region"] = d.region
    c["d1_deficit_acces"] = (100 - d.tbs_T).clip(lower=0)
    c["d2_retard_filles_acces"] = (((1 - d.ips_tba).clip(lower=0) + (1 - d.ips_tbs).clip(lower=0)) / 2) * 100
    c["d3_retard_garcons_achevement"] = (d.ips_tap - 1).clip(lower=0) * 100
    c["d4_ecart_urbain_rural_filles"] = ur.ecart_filles_urbain_rural_pts.clip(lower=0).reindex(c.index).fillna(0)
    c["d5_fragilite"] = (-d.perte_depuis_pic_pct).clip(lower=0) + 0.0
    return c


def ida(c, poids=None):
    dims = list(DIMENSIONS)
    poids = np.ones(len(dims)) / len(dims) if poids is None else np.asarray(poids)
    x = c[dims]
    norm = (x - x.min()) / (x.max() - x.min()).replace(0, 1)
    return 100 * (norm.values @ poids), norm


def indice_et_sensibilite():
    c = composantes()
    score, norm = ida(c)
    out = c.copy()
    for k in DIMENSIONS:
        out[k + "_norm"] = norm[k]
    out["ida"] = score
    out["rang"] = out.ida.rank(ascending=False, method="min").astype(int)
    # Sensibilite : 2000 jeux de poids tires au hasard (Dirichlet), on regarde si le classement tient
    rng = np.random.default_rng(2026)
    W = rng.dirichlet(np.ones(len(DIMENSIONS)), 2000)
    rangs = np.array([pd.Series(ida(c, w)[0], index=c.index).rank(ascending=False, method="min").values for w in W])
    out["rang_median_sensibilite"] = np.median(rangs, axis=0)
    out["rang_p10"] = np.percentile(rangs, 10, axis=0)
    out["rang_p90"] = np.percentile(rangs, 90, axis=0)
    out["pct_tirages_top4"] = 100 * (rangs <= 4).mean(axis=0)
    # Variante "sans fragilite" et variante "IPS des effectifs" (insensible au denominateur de population)
    c2 = c.copy()
    d = REG[REG.annee_fin == DERNIERE].set_index("region_code")
    c2["d2_retard_filles_acces"] = (1 - d.eff_F / d.eff_G * (d.pop611_G / d.pop611_F)).clip(lower=0) * 100
    out["ida_variante_ips_effectifs"] = ida(c2)[0]
    quatre = c[list(DIMENSIONS)[:4]]
    out["ida_sans_fragilite"] = 100 * ((quatre - quatre.min()) / (quatre.max() - quatre.min())).mean(axis=1)
    rho = pd.Series(out.ida).rank().corr(pd.Series(out.ida_sans_fragilite).rank())
    rho2 = pd.Series(out.ida).rank().corr(pd.Series(out.ida_variante_ips_effectifs).rank())
    out = out.reset_index().sort_values("rang")
    sauver(out, "scientist", "indice-disparites-acces-IDA-2024-2025")
    meta = {"spearman_ida_vs_sans_fragilite": round(float(rho), 3),
            "spearman_ida_vs_variante_ips_effectifs": round(float(rho2), 3),
            "tirages_de_poids": 2000, "graine": 2026, "dimensions": DIMENSIONS}
    (D04 / nom(4, "scientist", "IDA-parametres-et-robustesse", "json")).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return out, meta


def typologie(ida_df):
    d = REG[REG.annee_fin == DERNIERE].set_index("region_code")
    ur = P[(P.niveau == "region") & (P.annee_fin == DERNIERE)].set_index("region_code")
    rows = []
    for rc, r in d.iterrows():
        if r.tbs_T < 65 and r.perte_depuis_pic_pct < -10:
            prof, action = "A. Acces effondre par la crise", "Rouvrir ou relocaliser les ecoles, scolarisation d'urgence des eleves deplaces, suivi mensuel ESU"
        elif r.tbs_T < 65:
            prof, action = "A. Acces effondre par la crise", "Rouvrir ou relocaliser les ecoles, scolarisation d'urgence, suivi mensuel ESU"
        elif r.tbs_T < 90 and r.ips_tbs < 0.98:
            prof, action = "B. Acces moyen, filles en retard", "Cibler l'inscription des filles au CP1 (sensibilisation, cantines, kits), surtout en zone rurale"
        elif r.tbs_T < 90:
            prof, action = "C. Acces moyen, ecart surtout territorial", "Etendre l'offre (classes, ecoles) vers les zones rurales peu couvertes"
        elif r.ips_tap >= 1.15:
            prof, action = "D. Acces eleve, garcons decrochent avant la fin", "Lutter contre l'abandon des garcons en CM (soutien scolaire, suivi des absences, travail des enfants)"
        else:
            prof, action = "E. Acces eleve et parite proche", "Maintenir ; surveiller l'accueil des eleves deplaces"
        rows.append({"region_code": rc, "region": r.region, "profil": prof, "levier_prioritaire": action,
                     "tbs_T": r.tbs_T, "ips_tbs": r.ips_tbs, "ips_tap": r.ips_tap,
                     "perte_depuis_pic_pct": r.perte_depuis_pic_pct,
                     "part_filles_rural": ur.loc[rc, "rural_pct_filles"], "part_filles_urbain": ur.loc[rc, "urbain_pct_filles"],
                     "ida": float(ida_df.set_index("region_code").loc[rc, "ida"])})
    df = pd.DataFrame(rows).sort_values(["profil", "ida"], ascending=[True, False])
    sauver(df, "analyst", "typologie-des-regions-2024-2025")
    return df


def alertes_provinces():
    p = P[(P.niveau == "province") & (P.annee_fin == DERNIERE)].copy()
    p["alerte_filles_rural"] = p.rural_pct_filles < 47
    p["alerte_ecart_ville_campagne"] = p.ecart_filles_urbain_rural_pts >= 2
    # Hors Kadiogo et Houet (Ouagadougou, Bobo-Dioulasso), une majorite d'eleves en ville signale
    # que l'ecole rurale s'est videe (fermetures, deplacements).
    p["alerte_effectif_rural_minoritaire"] = (p.part_urbain_pct > 50) & ~p.province.isin(["Kadiogo", "Houet"])
    p["nb_alertes"] = p[["alerte_filles_rural", "alerte_ecart_ville_campagne", "alerte_effectif_rural_minoritaire"]].sum(axis=1)
    p = p.sort_values(["nb_alertes", "rural_pct_filles"], ascending=[False, True])
    cols = ["region", "province", "ensemble_total", "part_urbain_pct", "urbain_pct_filles", "rural_pct_filles",
            "ecart_filles_urbain_rural_pts", "var_rural_pct", "var_urbain_pct", "alerte_filles_rural",
            "alerte_ecart_ville_campagne", "alerte_effectif_rural_minoritaire", "nb_alertes"]
    sauver(p[cols], "analyst", "alertes-provinces-urbain-rural-2024-2025")
    return p


def lien_crise():
    """Les regions ou les fermetures ont ete les plus nombreuses sont-elles celles ou le TBS a le plus chute ?
    Simple association (13 regions), pas une preuve de causalite."""
    d = REG.pivot(index="region_code", columns="annee_fin", values="tbs_T")
    e = REG[REG.annee_fin == 2022].set_index("region_code").ecoles_total
    x = REG[REG.annee_fin == 2023].set_index("region_code")[["region", "etablissements_fermes", "pdi_pour_100_enfants_611"]].copy()
    x["fermetures_pour_100_ecoles_primaires"] = 100 * x.etablissements_fermes / e
    x["chute_tbs_2018_2023_pts"] = d[2023] - d[2018]
    rho_f = x.fermetures_pour_100_ecoles_primaires.rank().corr(x.chute_tbs_2018_2023_pts.rank())
    rho_p = x.pdi_pour_100_enfants_611.rank().corr(x.chute_tbs_2018_2023_pts.rank())
    x["spearman_fermetures_vs_chute"] = rho_f
    x["spearman_pdi_vs_chute"] = rho_p
    sauver(x.reset_index(), "analyst", "lien-fermetures-ESU-et-chute-du-TBS")
    return rho_f, rho_p


# ---------------------------------------------------------------------------
# Q4. Projection 2030, avec test retrospectif
# ---------------------------------------------------------------------------
def projection():
    """
    Modele volontairement simple et explicable : tendance lineaire par region.
    On le teste d'abord : apprentissage 2016-2021, prevision 2022-2025, compare a la
    prevision naive (derniere valeur connue). Si la tendance ne bat pas la naive, on le dit.
    Pour 2030, on retient deux scenarios : prolongation de la reprise 2023-2025, et
    stagnation au niveau 2025.
    """
    test = []
    for v in ("tbs_T", "ips_tbs", "part_filles"):
        for rc, d in REG.groupby("region_code"):
            d = d.set_index("annee_fin")[v]
            tr, te = d.loc[2016:2021], d.loc[2022:2025]
            a, b = np.polyfit(tr.index, tr.values, 1)
            pred = a * te.index.values + b
            test.append({"variable": v, "region_code": rc, "mae_tendance": np.abs(pred - te.values).mean(),
                         "mae_naive": np.abs(tr.iloc[-1] - te.values).mean()})
    test = pd.DataFrame(test)
    bilan = test.groupby("variable")[["mae_tendance", "mae_naive"]].mean().reset_index()
    bilan["tendance_bat_naive"] = bilan.mae_tendance < bilan.mae_naive
    sauver(bilan, "scientist", "projection-test-retrospectif-2022-2025")

    rows = []
    for rc, d in pd.concat([REG, T[T.region_code == "BF"]]).groupby("region_code"):
        d = d.set_index("annee_fin")
        pente = (d.loc[2025, "tbs_T"] - d.loc[2023, "tbs_T"]) / 2
        pente_f = (d.loc[2025, "tbs_F"] - d.loc[2023, "tbs_F"]) / 2
        # La reprise est plafonnee au meilleur niveau atteint avant la crise (2016-2021) :
        # on ne suppose pas qu'une region depasse son propre record par simple rattrapage.
        plafond = max(d.loc[2016:2021, "tbs_T"].max(), d.loc[2025, "tbs_T"])
        tbs30 = min(d.loc[2025, "tbs_T"] + 5 * max(pente, 0), plafond) if pente > 0 else d.loc[2025, "tbs_T"] + 5 * pente
        annee_80 = None
        if d.loc[2025, "tbs_T"] >= 80:
            annee_80 = 2025
        elif pente > 0:
            annee_80 = int(np.ceil(2025 + (80 - d.loc[2025, "tbs_T"]) / pente))
        pop30 = d.loc[2025, "pop611_T"] * (1.028 ** 5)  # croissance moyenne observee 2017-2024 du denominateur
        rows.append({"region_code": rc, "region": REGIONS.get(rc, "Burkina Faso"),
                     "tbs_T_2023": d.loc[2023, "tbs_T"], "tbs_T_2025": d.loc[2025, "tbs_T"],
                     "rythme_2023_2025_pts_par_an": pente, "rythme_2023_2025_filles_pts_par_an": pente_f,
                     "plafond_avant_crise": plafond, "tbs_T_2030_scenario_rythme_recent": tbs30, "tbs_T_2030_scenario_stagnation": d.loc[2025, "tbs_T"],
                     "annee_atteinte_tbs_80_rythme_recent": annee_80,
                     "pop611_2030_estimee": pop30,
                     "hors_ecole_2030_scenario_rythme_recent": max(pop30 * (1 - tbs30 / 100), 0),
                     "hors_ecole_2030_scenario_stagnation": max(pop30 * (1 - d.loc[2025, "tbs_T"] / 100), 0)})
    proj = pd.DataFrame(rows)
    sauver(proj, "scientist", "projection-2030-scenarios")
    return bilan, proj


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def figures(conv, poids, ida_df, proj):
    FIG.mkdir(parents=True, exist_ok=True)
    ans = list(range(2016, 2026))
    lab = [f"{a-1}-{str(a)[2:]}" for a in ans]

    # F1. TBS par region : l'ecart territorial
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ordre = REG[REG.annee_fin == 2025].sort_values("tbs_T").region_code
    for rc in ordre:
        d = REG[REG.region_code == rc].sort_values("annee_fin")
        fort = rc in ("BF56", "BF52", "BF49", "BF46", "BF13")
        ax.plot(ans, d.tbs_T, color=BLEU if fort else "#c3c2b7", lw=2 if fort else 1.2, zorder=3 if fort else 2)
        if fort:
            ax.text(2025.15, d.tbs_T.iloc[-1] + {"BF52": 2.5, "BF56": -2.5}.get(rc, 0), REGIONS[rc], va="center", fontsize=8, color=ENCRE2)
    ax.plot(ans, NAT.tbs_T, color=ENCRE, lw=2, ls="--")
    ax.text(2025.15, NAT.loc[2025, "tbs_T"] - 3, "Burkina Faso", va="center", fontsize=8, color=ENCRE, weight="bold")
    ax.set_xticks(ans, lab, rotation=0, fontsize=7)
    ax.set_xlim(2015.7, 2027.4)
    ax.set_ylabel("TBS primaire (%)")
    ax.set_title("Taux brut de scolarisation (TBS) par région, 2015-2016 à 2024-2025")
    fig.savefig(FIG / nom(4, "analyst", "F1-tbs-par-region", "png")); plt.close(fig)

    # F2. Ecart entre la region la mieux et la moins bien scolarisee
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    ax.fill_between(ans, conv.tbs_min, conv.tbs_max, color="#cde2fb", lw=0)
    ax.plot(ans, conv.tbs_max, color=BLEU, lw=2); ax.plot(ans, conv.tbs_min, color=BLEU, lw=2)
    for a, lo, hi in zip(ans, conv.tbs_min, conv.tbs_max):
        if a in (2016, 2019, 2023, 2025):
            ax.text(min(max(a, 2016.4), 2024.6), (lo + hi) / 2, f"{hi-lo:.0f} pts", ha="center", fontsize=8, color=ENCRE, weight="bold")
    ax.set_xticks(ans, lab, fontsize=7); ax.set_ylabel("TBS (%)")
    ax.set_title("Écart de TBS entre la région la plus et la moins scolarisée")
    fig.savefig(FIG / nom(4, "analyst", "F2-ecart-max-min-regions", "png")); plt.close(fig)

    # F3. Parite : IPS TBS et IPS TAP 2024-25 par region
    d = REG[REG.annee_fin == 2025].sort_values("ips_tbs")
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    y = np.arange(len(d))
    ax.axvline(1, color=ENCRE2, lw=1)
    ax.axvspan(0.97, 1.03, color="#f0efec", zorder=0)
    ax.scatter(d.ips_tbs, y, s=40, color=ORANGE, label="IPS du TBS (accès)", zorder=3, edgecolor="white", lw=1.5)
    ax.scatter(d.ips_tap, y, s=40, color=BLEU, label="IPS du taux d'achèvement", zorder=3, edgecolor="white", lw=1.5)
    for yi, a, b in zip(y, d.ips_tbs, d.ips_tap):
        ax.plot([a, b], [yi, yi], color="#c3c2b7", lw=1, zorder=2)
    ax.set_yticks(y, d.region)
    ax.set_xlabel("Indice de parité filles / garçons  (< 1 : filles en retard   |   > 1 : garçons en retard)")
    ax.legend(loc="lower right", fontsize=8)
    ax.set_title("Parité en 2024-2025 : les filles entrent moins, les garçons finissent moins")
    fig.savefig(FIG / nom(4, "analyst", "F3-parite-acces-vs-achevement", "png")); plt.close(fig)

    # F4. Urbain / rural au niveau national
    m = MIL[MIL.sexe == "T"].pivot(index="annee_fin", columns="milieu", values="valeur")
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    ax.plot(ans, m.Rural / 1e6, color=ORANGE, lw=2, marker="o", ms=4, label="Rural")
    ax.plot(ans, m.Urbain / 1e6, color=BLEU, lw=2, marker="o", ms=4, label="Urbain")
    ax.text(2025.2, m.Rural.iloc[-1] / 1e6, "Rural", color=ENCRE2, va="center", fontsize=8)
    ax.text(2025.2, m.Urbain.iloc[-1] / 1e6, "Urbain", color=ENCRE2, va="center", fontsize=8)
    ax.set_xticks(ans, lab, fontsize=7); ax.set_ylabel("Élèves (millions)"); ax.set_xlim(2015.7, 2026.2)
    ax.set_title("Élèves du primaire selon le milieu : la campagne a perdu, la ville a gagné")
    ax.legend(loc="center left", fontsize=8)
    fig.savefig(FIG / nom(4, "analyst", "F4-urbain-rural-national", "png")); plt.close(fig)

    # F5. Poids des ecarts en nombre d'enfants
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    ax.plot(ans, poids.enfants_hors_ecole_estimation_basse / 1e3, color=ENCRE, lw=2, label="Enfants de 6-11 ans hors école (estimation basse)")
    ax.plot(ans, poids.enfants_manquants_rattrapage_moyenne_nationale / 1e3, color=BLEU, lw=2, label="Écart territorial : enfants manquants pour hisser chaque région à la moyenne nationale")
    ax.plot(ans, poids.filles_manquantes_parite / 1e3, color=ORANGE, lw=2, label="Écart filles-garçons : filles manquantes pour la parité")
    ax.set_xticks(ans, lab, fontsize=7); ax.set_ylabel("Milliers d'enfants")
    ax.legend(fontsize=7.5, loc="upper left")
    ax.set_title("Quel écart pèse le plus ? En nombre d'enfants")
    fig.savefig(FIG / nom(4, "analyst", "F5-poids-des-ecarts", "png")); plt.close(fig)

    # F6. IDA classement avec intervalle de sensibilite
    d = ida_df.sort_values("ida")
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    y = np.arange(len(d))
    ax.barh(y, d.ida, color=BLEU, height=0.6)
    for yi, v, lo, hi in zip(y, d.ida, d.rang_p10, d.rang_p90):
        ax.text(v + 1, yi, f"{v:.0f}   (rang {int(lo)}-{int(hi)})", va="center", fontsize=7.5, color=ENCRE2)
    ax.set_yticks(y, d.region); ax.set_xlim(0, 112)
    ax.set_xlabel("Indice des disparités d'accès (0 = la plus favorable, 100 = la plus défavorable)")
    ax.set_title("Indice IDA 2024-2025 (entre parenthèses : rangs possibles sur 2 000 jeux de poids)")
    ax.grid(axis="y", visible=False)
    fig.savefig(FIG / nom(4, "scientist", "F6-classement-IDA", "png")); plt.close(fig)

    # F7. Part des filles par niveau (national)
    n = NIV.pivot_table(index=["annee_fin", "niveau"], columns="sexe", values="effectif").reset_index()
    n["pf"] = 100 * n.F / n["T"]
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    niveaux = ["CP1", "CP2", "CE1", "CE2", "CM1", "CM2"]
    for a, col in ((2016, "#86b6ef"), (2021, "#3987e5"), (2025, "#104281")):
        x = n[n.annee_fin == a].set_index("niveau").loc[niveaux, "pf"]
        ax.plot(niveaux, x, marker="o", ms=5, lw=2, color=col, label=f"{a-1}-{a}")
    ax.axhline(50, color=ENCRE2, lw=1, ls=":")
    ax.set_ylabel("Part des filles (%)"); ax.legend(fontsize=8)
    ax.set_title("Part des filles du CP1 au CM2 : minoritaires à l'entrée, majoritaires à la sortie")
    fig.savefig(FIG / nom(4, "analyst", "F7-part-filles-par-niveau", "png")); plt.close(fig)


if __name__ == "__main__":
    D04.mkdir(parents=True, exist_ok=True)
    tend = tendances()
    conv = convergence()
    poids = poids_des_ecarts()
    ida_df, meta = indice_et_sensibilite()
    typ = typologie(ida_df)
    alertes = alertes_provinces()
    bilan, proj = projection()
    print("[04] lien crise (Spearman fermetures, PDI) :", [round(v, 2) for v in lien_crise()])
    figures(conv, poids, ida_df, proj)
    pd.set_option("display.width", 220)
    print(conv[["annee_fin", "tbs_min", "tbs_max", "ecart_max_min_pts", "coef_variation_tbs_pct", "theil_eleves_vs_population", "ecart_moyen_parite_tbs", "part_urbain_national_pct"]].round(3).to_string(index=False))
    print(poids.round(0).to_string(index=False))
    print(ida_df[["region", "ida", "rang", "rang_p10", "rang_p90", "pct_tirages_top4", "ida_variante_ips_effectifs", "ida_sans_fragilite"]].round(1).to_string(index=False))
    print(meta)
    print(typ[["region", "profil", "tbs_T", "ips_tbs", "ips_tap", "perte_depuis_pic_pct"]].round(2).to_string(index=False))
    print(bilan.round(3).to_string(index=False))
    print(proj.round(1).to_string(index=False))
    print(alertes[alertes.nb_alertes > 0][["region", "province", "rural_pct_filles", "ecart_filles_urbain_rural_pts", "part_urbain_pct", "nb_alertes"]].round(1).to_string(index=False))
