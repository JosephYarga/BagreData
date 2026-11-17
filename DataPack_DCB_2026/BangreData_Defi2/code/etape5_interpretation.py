"""
Etape 5 : interpretation et visualisation.

Produit :
  * le tableau de bord interactif (un seul fichier HTML, fonctionne hors connexion) ;
  * les fiches d'une page pour chaque directeur regional (PDF, 13 pages) ;
  * les messages cles pour le decideur (CSV).
"""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Polygon as MplPolygon
import numpy as np
import pandas as pd

from config import D02, D03, D04, D05, PROJET, REGIONS, nom

rd3 = lambda r, d: pd.read_csv(D03 / nom(3, r, d, "csv"), sep=";", encoding="utf-8-sig")
rd4 = lambda r, d: pd.read_csv(D04 / nom(4, r, d, "csv"), sep=";", encoding="utf-8-sig")

T = rd3("engineer", "table-indicateurs-region-annee")
P = rd3("engineer", "table-urbain-rural-provinces-2024-2025")
IDA = rd4("scientist", "indice-disparites-acces-IDA-2024-2025")
TYP = rd4("analyst", "typologie-des-regions-2024-2025")
CONV = rd4("analyst", "convergence-entre-regions-2016-2025")
POIDS = rd4("analyst", "poids-des-ecarts-en-nombre-d-enfants")
PROJ = rd4("scientist", "projection-2030-scenarios")
ALERTES = rd4("analyst", "alertes-provinces-urbain-rural-2024-2025")
META = json.loads((D04 / nom(4, "scientist", "IDA-parametres-et-robustesse", "json")).read_text(encoding="utf-8"))
MIL = pd.read_csv(D02 / nom(2, "engineer", "primaire-effectifs-milieu-national", "csv"), sep=";", encoding="utf-8-sig")
NIV = pd.read_csv(D02 / nom(2, "engineer", "primaire-effectifs-niveau-sexe-national", "csv"), sep=";", encoding="utf-8-sig")
ANNEES = list(range(2016, 2026))
PROFILS = {  # libelles accentues pour l'affichage
    "A. Acces effondre par la crise": "Accès effondré par la crise",
    "B. Acces moyen, filles en retard": "Accès moyen, filles en retard",
    "C. Acces moyen, ecart surtout territorial": "Accès moyen, écart surtout territorial",
    "D. Acces eleve, garcons decrochent avant la fin": "Accès élevé, garçons qui décrochent avant la fin",
    "E. Acces eleve et parite proche": "Accès élevé et parité proche",
}
LEVIERS = {
    "A": "Rouvrir ou relocaliser les écoles fermées, organiser la scolarisation d'urgence des élèves déplacés et suivre chaque mois les réouvertures (données ESU).",
    "B": "Cibler l'inscription des filles au CP1, d'abord en zone rurale : sensibilisation des familles, cantines, kits scolaires, suivi des filles non réinscrites.",
    "C": "Étendre l'offre (classes, écoles) vers les zones rurales les moins couvertes.",
    "D": "Retenir les garçons jusqu'au CM2 : suivi des absences, soutien scolaire en CM, dialogue avec les familles sur le travail des enfants.",
    "E": "Maintenir le niveau atteint et préparer l'accueil des élèves déplacés venus d'autres régions.",
}


# ---------------------------------------------------------------------------
# Geometrie : GeoJSON -> chemins SVG (projection equirectangulaire corrigee)
# ---------------------------------------------------------------------------
def charger_geo(fichier):
    return json.loads((D03 / fichier).read_text(encoding="utf-8"))["features"]


GEO_R = charger_geo(nom(3, "architect", "fond-de-carte-13-regions-ancien-decoupage", "geojson"))
GEO_P = charger_geo(nom(3, "architect", "fond-de-carte-45-provinces-ancien-decoupage", "geojson"))


def anneaux(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    return [ring for poly in polys for ring in poly]


tous = [pt for f in GEO_R for r in anneaux(f["geometry"]) for pt in r]
LON0, LON1 = min(p[0] for p in tous), max(p[0] for p in tous)
LAT0, LAT1 = min(p[1] for p in tous), max(p[1] for p in tous)
K = np.cos(np.radians((LAT0 + LAT1) / 2))
W, H, M = 640, 520, 12
ECH = min((W - 2 * M) / ((LON1 - LON0) * K), (H - 2 * M) / (LAT1 - LAT0))


def proj(lon, lat):
    return M + (lon - LON0) * K * ECH, M + (LAT1 - lat) * ECH


def chemin(geom):
    d = []
    for ring in anneaux(geom):
        pts = [proj(*p) for p in ring]
        d.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
    return "".join(d)


def centre(geom):
    # centre du plus grand anneau, suffisant pour placer une etiquette
    ring = max(anneaux(geom), key=len)
    pts = np.array([proj(*p) for p in ring])
    x, y = pts[:, 0], pts[:, 1]
    a = 0.5 * np.sum(x[:-1] * y[1:] - x[1:] * y[:-1])
    cx = np.sum((x[:-1] + x[1:]) * (x[:-1] * y[1:] - x[1:] * y[:-1])) / (6 * a)
    cy = np.sum((y[:-1] + y[1:]) * (x[:-1] * y[1:] - x[1:] * y[:-1])) / (6 * a)
    return round(cx, 1), round(cy, 1)


# ---------------------------------------------------------------------------
# Donnees du tableau de bord
# ---------------------------------------------------------------------------
def serie(d, v, nd=4):
    return [None if pd.isna(x) else round(float(x), nd) for x in d.set_index("annee_fin").reindex(ANNEES)[v]]


VARS = ["tbs_T", "tbs_F", "tbs_G", "tba_T", "ips_tbs", "ips_tba", "ips_tap", "tap_T", "tap_F", "tap_G", "eff_T", "eff_F",
        "part_filles", "hors_ecole_T", "hors_ecole_F", "perte_depuis_pic_pct"]


def donnees():
    regions = {}
    ida = IDA.set_index("region_code")
    typ = TYP.set_index("region_code")
    proj_ = PROJ.set_index("region_code")
    urr = P[(P.niveau == "region") & (P.annee_fin == 2025)].set_index("region_code")
    for rc, nm in REGIONS.items():
        d = T[T.region_code == rc]
        i = ida.loc[rc]
        last = d[d.annee_fin == 2025].iloc[0]
        prof = typ.loc[rc, "profil"]
        regions[rc] = {
            "code": rc, "nom": nm, "profil": PROFILS[prof], "levier": LEVIERS[prof[0]],
            "s": {v: serie(d, v) for v in VARS},
            "ida": {"ida": round(float(i.ida), 1), "rang": int(i.rang), "p10": int(i.rang_p10), "p90": int(i.rang_p90),
                    "d1": float(i.d1_deficit_acces), "d2": float(i.d2_retard_filles_acces), "d3": float(i.d3_retard_garcons_achevement),
                    "d4": float(i.d4_ecart_urbain_rural_filles), "d5": float(i.d5_fragilite)},
            "ur": {"pf_urb": float(urr.loc[rc, "urbain_pct_filles"]), "pf_rur": float(urr.loc[rc, "rural_pct_filles"]),
                   "ecart": float(urr.loc[rc, "ecart_filles_urbain_rural_pts"]), "part_urbain": float(urr.loc[rc, "part_urbain_pct"])},
            "esu": {"fermes": int(last.etablissements_fermes), "eleves": int(last.eleves_affectes)},
            "pdi": int(last.pdi_total),
            "proj": {"tbs30": float(proj_.loc[rc, "tbs_T_2030_scenario_rythme_recent"]),
                     "plafond": float(proj_.loc[rc, "plafond_avant_crise"]),
                     "rythme": float(proj_.loc[rc, "rythme_2023_2025_pts_par_an"]),
                     "an80": None if pd.isna(proj_.loc[rc, "annee_atteinte_tbs_80_rythme_recent"]) else int(proj_.loc[rc, "annee_atteinte_tbs_80_rythme_recent"])},
        }
    nat = T[T.region_code == "BF"]
    conv = [{"annee": int(r.annee_fin), "min": r.tbs_min, "max": r.tbs_max, "ecart": r.ecart_max_min_pts,
             "min_nom": r.region_tbs_min, "max_nom": T[(T.annee_fin == r.annee_fin) & (T.region_code != "BF")].sort_values("tbs_T").region.iloc[-1],
             "urbain": r.part_urbain_national_pct} for r in CONV.itertuples()]
    poids = [{"annee": int(r.annee_fin), "filles": r.filles_manquantes_parite, "territ": r.enfants_manquants_rattrapage_moyenne_nationale,
              "hors": r.enfants_hors_ecole_estimation_basse} for r in POIDS.itertuples()]
    m = MIL[MIL.sexe == "T"].pivot(index="annee_fin", columns="milieu", values="valeur")
    n = NIV.pivot_table(index=["annee_fin", "niveau"], columns="sexe", values="effectif").reset_index()
    n["pf"] = 100 * n.F / n["T"]
    niv = {str(a): [round(float(n[(n.annee_fin == a) & (n.niveau == l)].pf.iloc[0]), 2) for l in ["CP1", "CP2", "CE1", "CE2", "CM1", "CM2"]] for a in (2016, 2025)}

    geo_reg = []
    for f in GEO_R:
        cx, cy = centre(f["geometry"])
        geo_reg.append({"code": f["properties"]["code"], "nom": f["properties"]["nom"], "d": chemin(f["geometry"]), "cx": cx, "cy": cy})
    geo_prov = []
    for f in GEO_P:
        nm = f["properties"]["nom"]
        mm = {}
        for a in (2024, 2025):
            x = P[(P.niveau == "province") & (P.province == nm) & (P.annee_fin == a)]
            if len(x):
                x = x.iloc[0]
                mm[str(a)] = {"total": int(x.ensemble_total), "part_urbain": round(x.part_urbain_pct, 2),
                              "urbain_pct_filles": x.urbain_pct_filles, "rural_pct_filles": x.rural_pct_filles,
                              "rural_pct_filles_": x.rural_pct_filles, "ecart": round(x.ecart_filles_urbain_rural_pts, 2),
                              "var_rural": None if pd.isna(x.var_rural_pct) else round(x.var_rural_pct, 2)}
        geo_prov.append({"code": f["properties"]["code"], "nom": nm, "region": REGIONS[f["properties"]["region_code"]],
                         "d": chemin(f["geometry"]), "m": mm})
    alertes = [{"province": r.province, "region": r.region, "rural_pct_filles": r.rural_pct_filles,
                "ecart": r.ecart_filles_urbain_rural_pts, "part_urbain": r.part_urbain_pct, "n": int(r.nb_alertes)}
               for r in ALERTES[ALERTES.nb_alertes > 0].itertuples()]
    return {
        "annees": ANNEES, "regions": regions,
        "nat": {v: serie(nat, v) for v in VARS},
        "conv": conv, "poids": poids,
        "milieu": {"rural": [float(x) for x in m.Rural], "urbain": [float(x) for x in m.Urbain]},
        "niveaux": niv, "geo_reg": geo_reg, "geo_prov": geo_prov, "alertes": alertes,
        "meta": {"rho1": META["spearman_ida_vs_sans_fragilite"], "rho2": META["spearman_ida_vs_variante_ips_effectifs"]},
        "messages": messages_cles(),
    }


def fr(x, d=0):
    s = f"{x:,.{d}f}".replace(",", " ").replace(".", ",")
    return s


def messages_cles():
    c0, c9 = CONV.iloc[0], CONV.iloc[-1]
    p = POIDS.set_index("annee_fin")
    reg25 = T[(T.annee_fin == 2025) & (T.region_code != "BF")]
    nat = T[T.region_code == "BF"].set_index("annee_fin")
    m = MIL[MIL.sexe == "T"].pivot(index="annee_fin", columns="milieu", values="valeur")
    filles_retard = reg25[reg25.ips_tbs < 0.97].sort_values("ips_tbs").region.tolist()
    entree_retard = reg25[reg25.ips_tba < 0.97].region.tolist()
    garcons_fin = reg25[reg25.ips_tap > 1.03].region.tolist()
    pr = PROJ.set_index("region")
    ratio = p.loc[2025, "enfants_manquants_rattrapage_moyenne_nationale"] / max(p.loc[2023:2025, "filles_manquantes_parite"].max(), 1)
    n = NIV.pivot_table(index=["annee_fin", "niveau"], columns="sexe", values="effectif")
    pf_cp1 = 100 * n.loc[(2025, "CP1"), "F"] / n.loc[(2025, "CP1"), "T"]
    pf_cm2 = 100 * n.loc[(2025, "CM2"), "F"] / n.loc[(2025, "CM2"), "T"]
    top_prov = ALERTES.sort_values("rural_pct_filles").iloc[0]
    msgs = [
        {"chiffre": f"{fr(c0.ecart_max_min_pts)} → {fr(c9.ecart_max_min_pts)} pts",
         "titre": "L'écart entre régions s'est creusé",
         "texte": f"En 2015-2016, {fr(c0.ecart_max_min_pts)} points de TBS séparaient la région la plus scolarisée de la moins scolarisée. En 2024-2025, l'écart est de {fr(c9.ecart_max_min_pts)} points : l'Est ({fr(reg25.set_index('region').loc['Est','tbs_T'],0)} %) et le Sahel ({fr(reg25.set_index('region').loc['Sahel','tbs_T'],0)} %) sont loin derrière le Centre ({fr(reg25.set_index('region').loc['Centre','tbs_T'],0)} %)."},
        {"chiffre": f"≈ {fr(ratio)} fois",
         "titre": "L'écart territorial pèse bien plus que l'écart filles-garçons",
         "texte": f"Pour amener chaque région au TBS national, il faudrait scolariser environ {fr(p.loc[2025,'enfants_manquants_rattrapage_moyenne_nationale']/1000)} 000 enfants de plus. Combler partout le retard des filles sur les garçons n'en demanderait que quelques milliers à quelques dizaines de milliers selon l'année."},
        {"chiffre": f"{len(filles_retard)} régions",
         "titre": "La parité nationale cache des filles en retard",
         "texte": f"Au niveau national l'IPS du TBS est de {fr(nat.loc[2025,'ips_tbs'],2)}. Mais les filles restent en retard dans : {', '.join(filles_retard)}. À l'entrée au CP1, elles sont en retard dans {len(entree_retard)} régions sur 13."},
        {"chiffre": f"{fr(pf_cp1,1)} % → {fr(pf_cm2,1)} %",
         "titre": "En fin de cycle, ce sont les garçons qui manquent",
         "texte": f"Les filles sont minoritaires au CP1 ({fr(pf_cp1,1)} %) mais majoritaires au CM2 ({fr(pf_cm2,1)} %). L'IPS du taux d'achèvement dépasse 1,03 dans {len(garcons_fin)} régions : les garçons quittent l'école avant la fin."},
        {"chiffre": f"{fr(c0.part_urbain_national_pct,0)} % → {fr(c9.part_urbain_national_pct,0)} %",
         "titre": "L'école se vide à la campagne",
         "texte": f"Le primaire rural a perdu {fr((m.loc[2021,'Rural']-m.loc[2023,'Rural'])/1000)} 000 élèves entre 2020-2021 et 2022-2023, quand la ville en gagnait. La part des élèves scolarisés en ville est passée de {fr(c0.part_urbain_national_pct,0)} % à {fr(c9.part_urbain_national_pct,0)} %."},
        {"chiffre": f"{int(pr.loc['Est','annee_atteinte_tbs_80_rythme_recent'])} et {int(pr.loc['Sahel','annee_atteinte_tbs_80_rythme_recent'])}",
         "titre": "Au rythme actuel, le rattrapage prendra plus de dix ans",
         "texte": f"Si la reprise observée entre 2022-2023 et 2024-2025 se poursuit, l'Est n'atteindrait un TBS de 80 % que vers {int(pr.loc['Est','annee_atteinte_tbs_80_rythme_recent'])} et le Sahel vers {int(pr.loc['Sahel','annee_atteinte_tbs_80_rythme_recent'])}. Le Centre-Nord y parviendrait vers {int(pr.loc['Centre-Nord','annee_atteinte_tbs_80_rythme_recent'])}."},
        {"chiffre": f"{fr(top_prov.rural_pct_filles,1)} %",
         "titre": "Des provinces où les filles rurales décrochent",
         "texte": f"À {top_prov.province} ({top_prov.region}), les filles ne représentent que {fr(top_prov.rural_pct_filles,1)} % des élèves ruraux. {int((ALERTES.nb_alertes>0).sum())} provinces présentent au moins un signal d'alerte ville-campagne en 2024-2025."},
    ]
    return msgs


def tableau_de_bord(data):
    modele = (PROJET / "code" / "modele_tableau_de_bord.html").read_text(encoding="utf-8")
    html = modele.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    sortie = D05 / nom(5, "analyst", "tableau-de-bord-ecarts-acces", "html")
    sortie.write_text(html, encoding="utf-8")
    return sortie


# ---------------------------------------------------------------------------
# Fiches d'une page pour les directeurs regionaux (PDF)
# ---------------------------------------------------------------------------
def fiches(data):
    BLEU, ORANGE, ENCRE, ENCRE2 = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e"
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5})
    sortie = D05 / nom(5, "analyst", "fiches-decideur-13-regions", "pdf")
    lab = [f"{str(a-1)[2:]}-{str(a)[2:]}" for a in ANNEES]
    ordre = sorted(data["regions"].values(), key=lambda r: r["ida"]["rang"])
    with PdfPages(sortie) as pdf:
        for r in ordre:
            s, i = r["s"], len(ANNEES) - 1
            fig = plt.figure(figsize=(8.27, 11.69))
            fig.patch.set_facecolor("white")
            fig.text(0.06, 0.955, f"Fiche région : {r['nom']}", fontsize=18, weight="bold", color=ENCRE)
            fig.text(0.06, 0.935, "Écarts d'accès à l'école primaire, situation 2024-2025 et évolution depuis 2015-2016", fontsize=9.5, color=ENCRE2)
            fig.text(0.06, 0.912, f"Profil : {r['profil']}     |     IDA {fr(r['ida']['ida'])} / 100, rang {r['ida']['rang']} sur 13", fontsize=10, color="#0d366b", weight="bold")
            # Carte de situation
            axm = fig.add_axes([0.66, 0.80, 0.30, 0.17])
            for g in GEO_R:
                for ring in anneaux(g["geometry"]):
                    pts = [proj(*p) for p in ring]
                    axm.add_patch(MplPolygon(pts, closed=True, fc=BLEU if g["properties"]["code"] == r["code"] else "#e1e0d9", ec="white", lw=0.6))
            axm.set_xlim(0, W); axm.set_ylim(H, 0); axm.set_aspect("equal"); axm.axis("off")
            # Chiffres cles
            kpis = [("TBS 2024-2025", f"{fr(s['tbs_T'][i],1)} %", f"2015-2016 : {fr(s['tbs_T'][0],1)} %"),
                    ("IPS du TBS (accès)", fr(s["ips_tbs"][i], 2), "1 = parité ; < 1 filles en retard"),
                    ("IPS du TAP (achèvement)", fr(s["ips_tap"][i], 2), "> 1 garçons en retard"),
                    ("Enfants 6-11 ans hors école", fr(s["hors_ecole_T"][i]), f"dont filles : {fr(s['hors_ecole_F'][i])}"),
                    ("Élèves 2024-2025", fr(s["eff_T"][i]), f"{fr(s['part_filles'][i],1)} % de filles"),
                    ("Filles ville / campagne", f"{fr(r['ur']['pf_urb'],1)} / {fr(r['ur']['pf_rur'],1)} %", f"{fr(r['ur']['part_urbain'],0)} % des élèves en ville")]
            for k, (l, v, sb) in enumerate(kpis):
                x, y = 0.06 + (k % 3) * 0.20, 0.855 - (k // 3) * 0.065
                fig.text(x, y, l, fontsize=8, color=ENCRE2)
                fig.text(x, y - 0.022, v, fontsize=14, weight="bold", color=ENCRE)
                fig.text(x, y - 0.037, sb, fontsize=7, color="#898781")
            # Graphiques
            ax1 = fig.add_axes([0.08, 0.50, 0.40, 0.19])
            ax1.plot(lab, s["tbs_G"], color=BLEU, lw=2, label="Garçons")
            ax1.plot(lab, s["tbs_F"], color=ORANGE, lw=2, label="Filles")
            ax1.plot(lab, data["nat"]["tbs_T"], color="#898781", lw=1.5, ls="--", label="National")
            ax1.set_title("TBS des filles et des garçons (%)", fontsize=9.5, weight="bold", loc="left")
            ax2 = fig.add_axes([0.56, 0.50, 0.40, 0.19])
            ax2.axhline(1, color=ENCRE2, lw=0.8)
            ax2.plot(lab, s["ips_tbs"], color=ORANGE, lw=2, label="Accès (IPS du TBS)")
            ax2.plot(lab, s["ips_tap"], color=BLEU, lw=2, label="Achèvement (IPS du TAP)")
            ax2.set_title("Parité filles / garçons", fontsize=9.5, weight="bold", loc="left")
            for ax in (ax1, ax2):
                ax.tick_params(axis="x", labelsize=6.5); ax.legend(fontsize=7, frameon=False)
                ax.spines[["top", "right"]].set_visible(False); ax.grid(color="#e1e0d9", lw=0.5)
            # Texte de decision
            al = []
            if s["tbs_T"][i] < 65: al.append(f"Accès très faible : TBS de {fr(s['tbs_T'][i],1)} % contre {fr(data['nat']['tbs_T'][i],1)} % au niveau national.")
            if s["perte_depuis_pic_pct"][i] < -10: al.append(f"L'effectif reste {fr(-s['perte_depuis_pic_pct'][i])} % sous son plus haut niveau depuis 2015-2016.")
            if s["ips_tbs"][i] < 0.97: al.append(f"Les filles sont en retard à l'accès (IPS du TBS {fr(s['ips_tbs'][i],2)}).")
            elif s["ips_tba"][i] < 0.97: al.append(f"Les filles sont en retard à l'entrée au CP1 (IPS du TBA {fr(s['ips_tba'][i],2)}).")
            if s["ips_tap"][i] > 1.15: al.append(f"Les garçons achèvent nettement moins le primaire (IPS du TAP {fr(s['ips_tap'][i],2)}).")
            if r["ur"]["ecart"] >= 1.5: al.append(f"Écart ville-campagne pour les filles : {fr(r['ur']['ecart'],1)} points.")
            if r["esu"]["fermes"]: al.append(f"Au 31/12/2022 : {fr(r['esu']['fermes'])} établissements fermés, {fr(r['esu']['eleves'])} élèves touchés (tous ordres) ; {fr(r['pdi'])} PDI accueillies.")
            if not al: al.append("Aucun signal d'alerte sur les indicateurs suivis.")
            y = 0.44
            fig.text(0.06, y, "Points d'attention", fontsize=11, weight="bold"); y -= 0.025
            for a in al:
                fig.text(0.07, y, "•  " + a, fontsize=9, wrap=True); y -= 0.022
            y -= 0.012
            fig.text(0.06, y, "Levier prioritaire", fontsize=11, weight="bold"); y -= 0.025
            import textwrap
            for ligne in textwrap.wrap(r["levier"], 105):
                fig.text(0.07, y, ligne, fontsize=9); y -= 0.018
            y -= 0.015
            fig.text(0.06, y, "Horizon 2030", fontsize=11, weight="bold"); y -= 0.025
            p = r["proj"]
            if p["rythme"] > 0:
                t = (f"Entre 2022-2023 et 2024-2025, le TBS a gagné {fr(p['rythme'],1)} point(s) par an. Si ce rythme se maintient, il atteindrait "
                     f"environ {fr(p['tbs30'])} % en 2029-2030 (hypothèse plafonnée au meilleur niveau d'avant-crise, {fr(p['plafond'])} %).")
                if p["an80"] and p["an80"] > 2025:
                    t += f" Au même rythme et sans plafond, le seuil de 80 % ne serait franchi que vers {p['an80']}."
            else:
                t = (f"Le TBS a reculé de {fr(-p['rythme'],1)} point(s) par an entre 2022-2023 et 2024-2025 (une partie de ce recul vient de la révision "
                     f"des projections de population en 2024-2025). Prolongée, cette tendance mènerait à environ {fr(p['tbs30'])} % en 2029-2030 : à surveiller.")
            for ligne in textwrap.wrap(t, 105):
                fig.text(0.07, y, ligne, fontsize=9); y -= 0.018
            fig.text(0.06, 0.03, "Sources : DGESS/MENAPLN (données 2015-2016 à 2024-2025, annuaires CNS529 et CNS530), ST-ESU (décembre 2022),\n"
                     "CONASUR (décembre 2022), OCHA/COD-AB. Hors école : estimation basse (population 6-11 ans implicite au TBS moins effectif).\n"
                     "Équipe Bangre Data, Data Challenge Burkina 2026, défi 2.",
                     fontsize=7, color="#898781")
            pdf.savefig(fig); plt.close(fig)
    return sortie


if __name__ == "__main__":
    D05.mkdir(parents=True, exist_ok=True)
    data = donnees()
    print("[05] tableau de bord ->", tableau_de_bord(data).name)
    print("[05] fiches ->", fiches(data).name)
    pd.DataFrame(data["messages"]).to_csv(D05 / nom(5, "analyst", "messages-cles-pour-le-decideur", "csv"), index=False, sep=";", encoding="utf-8-sig")
    for m in data["messages"]:
        print("-", m["chiffre"], "|", m["titre"], "|", m["texte"])
