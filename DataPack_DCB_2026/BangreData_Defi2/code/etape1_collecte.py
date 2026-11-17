"""
Etape 1 : collecte.

On rassemble les donnees brutes utiles au defi 2 et on les depose telles quelles
(ou sous forme d'extrait fidele) dans 01_collecte, avec un registre des sources.

Sources :
  1. DGESS, donnees statistiques prescolaire et primaire 2016-2025 (fichier principal)
  2. DGESS, annuaires du primaire 2023-2024 (CNS529) et 2024-2025 (CNS530),
     tableau I.2 : eleves par province, sexe et milieu (urbain / rural)
  3. DGESS / ST-ESU, rapport statistique mensuel de decembre 2022 :
     etablissements fermes par region
  4. CONASUR, situation des PDI au 31 decembre 2022 (onglet STATISTIQUES)
  5. OCHA / COD-AB, limites administratives (P-codes ancien et nouveau decoupage)
"""
import csv
import re
import shutil

import pandas as pd

from config import D01, DATAPACK, SRC, nom


def lire_csv_datapack(chemin):
    with open(DATAPACK / chemin, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f, delimiter=";"))


def extrait_urbain_rural():
    """Recopie les lignes brutes du tableau I.2 (pages 17 et 18) des deux annuaires."""
    lignes = []
    for cle, annee in (("annuaire_2023_24", "2023-2024"), ("annuaire_2024_25", "2024-2025")):
        rows = lire_csv_datapack(SRC[cle])
        entete = rows[0]
        i_page, i_ligne, i_nb = entete.index("page"), entete.index("ligne"), entete.index("nb_cellules")
        for r in rows[1:]:
            if r[i_page] in ("17", "18"):
                cellules = [c for c in r[i_nb + 1:i_nb + 11]]
                lignes.append([annee, SRC[cle].split("/")[-1], r[i_page], r[i_ligne], r[i_nb]] + cellules)
    cols = ["annee_scolaire", "fichier_source", "page", "ligne", "nb_cellules"] + [f"c{i}" for i in range(1, 11)]
    df = pd.DataFrame(lignes, columns=cols)
    sortie = D01 / nom(1, "engineer", "annuaires-CNS529-CNS530-tableau-I2-urbain-rural-extrait-brut", "csv")
    df.to_csv(sortie, index=False, sep=";", encoding="utf-8-sig")
    return sortie, len(df)


def fermetures_esu():
    """Lit le paragraphe I.4 du rapport ESU (pages 3 et 4) et en tire une ligne par region."""
    rows = lire_csv_datapack(SRC["esu_dec2022"])
    entete = rows[0]
    i_page, i_c1 = entete.index("page"), entete.index("c1")
    texte = " ".join(" ".join(c for c in r[i_c1:i_c1 + 13] if c)
                     for r in rows[1:] if r[i_page] in ("3", "4"))
    texte = re.sub(r"\s+", " ", texte)
    # Les nombres du rapport utilisent l'espace comme separateur de milliers ("1 154").
    nb = r"(\d{1,3}(?: \d{3})*)"
    motif = re.compile(
        r"(Boucle du Mouhoun|Cascades|Centre-Est|Centre-Nord|Centre-Ouest|Centre-Sud|Est|Hauts-Bassins|Nord|Sahel|Sud-Ouest)"
        r"\s*:?\s*(?:\|\s*)?:?\s*" + nb + r" (?:établissements )?(?:\| )?(?:: )?(?:scolaires )?fermés, affectant "
        + nb + r" élèves dont " + nb + r" filles, ainsi (?:\| )?(?:que )?" + nb + r" (?:\| )?(?:que )?(?:enseignants )?dont "
        + nb + r" femmes")
    res = []
    for m in motif.finditer(texte):
        v = [int(x.replace(" ", "")) for x in m.groups()[1:]]
        res.append({"region": m.group(1), "etablissements_fermes": v[0], "eleves_affectes": v[1],
                    "dont_filles": v[2], "enseignants_affectes": v[3], "dont_femmes": v[4]})
    df = pd.DataFrame(res).drop_duplicates("region")
    # Le rapport ne cite pas le Centre ni le Plateau-Central : aucune fermeture declaree.
    for reg in ("Centre", "Plateau-Central"):
        if reg not in set(df.region):
            df.loc[len(df)] = {"region": reg, "etablissements_fermes": 0, "eleves_affectes": 0,
                               "dont_filles": 0, "enseignants_affectes": 0, "dont_femmes": 0}
    df["date_situation"] = "2022-12-31"
    df["source"] = "ST-ESU, rapport statistique mensuel decembre 2022, p.3-4 (CSV OCR du Data Pack)"
    sortie = D01 / nom(1, "engineer", "ESU-etablissements-fermes-par-region-dec2022", "csv")
    df.to_csv(sortie, index=False, sep=";", encoding="utf-8-sig")
    return sortie, df


def pdi_conasur():
    x = pd.read_excel(DATAPACK / SRC["pdi_dec2022"], sheet_name="STATISTIQUES")
    x = x.rename(columns={x.columns[0]: "region", x.columns[1]: "pdi_total"})[["region", "pdi_total"]]
    x = x[x.region.notna() & pd.to_numeric(x.pdi_total, errors="coerce").notna()]
    x["pdi_total"] = x.pdi_total.astype(int)
    x["date_situation"] = "2022-12-31"
    x["source"] = "CONASUR, situation des PDI par commune d'accueil au 31/12/2022, onglet STATISTIQUES"
    sortie = D01 / nom(1, "engineer", "PDI-CONASUR-par-region-dec2022", "csv")
    x.to_csv(sortie, index=False, sep=";", encoding="utf-8-sig")
    return sortie, x


def limites():
    """Copie l'archive GeoJSON COD-AB (elle sert a dessiner la carte des 13 regions et 45 provinces)."""
    cible = D01 / nom(1, "engineer", "COD-AB-limites-administratives-geojson", "zip")
    if not cible.exists():
        shutil.copy(DATAPACK / SRC["limites_geojson"], cible)
    return cible


def registre(fichiers):
    sources = [
        ("S1", "DGESS / MENAPLN", "Donnees statistiques prescolaire et primaire 2015-2016 a 2024-2025",
         "2025", "Espace challenge (fichier principal)", "Effectifs, nouveaux inscrits, TBA, TBS, TAP, CEP, IPS, ecoles par region et sexe", "13 anciennes regions ; milieu urbain/rural seulement au niveau national"),
        ("S2", "DGESS / MENAPLN", "Annuaire statistique de l'enseignement primaire 2023-2024 (CNS529), tableau I.2",
         "2024", SRC["annuaire_2023_24"], "Eleves par province, sexe et milieu", "CSV issu d'une extraction PDF, a remettre en forme"),
        ("S3", "DGESS / MENAPLN", "Annuaire statistique de l'enseignement primaire 2024-2025 (CNS530), tableau I.2",
         "2025", SRC["annuaire_2024_25"], "Eleves par province, sexe et milieu", "idem"),
        ("S4", "ST-ESU / MENAPLN", "Rapport statistique mensuel ESU, decembre 2022", "2023", SRC["esu_dec2022"],
         "Etablissements fermes, eleves et enseignants affectes par region", "PDF scanne, texte obtenu par OCR ; tous ordres d'enseignement confondus"),
        ("S5", "CONASUR", "Situation des personnes deplacees internes au 31 decembre 2022", "2023", SRC["pdi_dec2022"],
         "PDI par region d'accueil", "Region d'accueil et non d'origine"),
        ("S6", "OCHA / COD-AB (IGB)", "Limites administratives du Burkina Faso v03", "2025", SRC["limites_geojson"],
         "Contours, P-codes nouveau et ancien decoupage", "Nouveau decoupage (17 regions) ; correspondance par adm2_pcode_old"),
    ]
    df = pd.DataFrame(sources, columns=["id_source", "producteur", "publication", "annee_publication",
                                        "emplacement", "contenu_utilise", "limites_connues"])
    sortie = D01 / nom(1, "architect", "registre-des-sources", "csv")
    df.to_csv(sortie, index=False, sep=";", encoding="utf-8-sig")
    return sortie


if __name__ == "__main__":
    D01.mkdir(parents=True, exist_ok=True)
    f1, n = extrait_urbain_rural()
    print(f"[01] extrait tableau I.2 : {n} lignes -> {f1.name}")
    f2, esu = fermetures_esu()
    print(f"[01] fermetures ESU : {len(esu)} regions, total {esu.etablissements_fermes.sum()} -> {f2.name}")
    f3, pdi = pdi_conasur()
    print(f"[01] PDI CONASUR : {len(pdi)} lignes, total {pdi.pdi_total.sum()} -> {f3.name}")
    f4 = limites()
    print(f"[01] limites COD-AB -> {f4.name}")
    print(f"[01] registre -> {registre([f1, f2, f3, f4]).name}")
