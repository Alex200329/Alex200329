"""Cartes de profil GitHub (SVG) dessinées à partir des vraies données du compte, dépôts privés compris.

Usage (dans l'action du profil) :
    GITHUB_TOKEN=<jeton du compte> python scripts/cartes.py Dossou2003 dist/dossou

Produit : <préfixe>-stats.svg, -serie.svg, -langages.svg, -trophees.svg, -contributions.svg.
Aucune dépendance : bibliothèque standard uniquement. --demo : données d'exemple (essai local seulement).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request
from html import escape

API = "https://api.github.com/graphql"
FOND, CARTE, BORD = "#0B0E17", "#10141F", "#1F2638"
TEXTE, DISCRET = "#E6EDF3", "#8B96B5"
BLEU, VIOLET = "#3D5AFE", "#9B6BFF"
POLICE = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"


# ---------------------------------------------------------------- données

def graphql(requete: str, variables: dict, jeton: str) -> dict:
    """Appelle l'API GraphQL de GitHub et renvoie le champ data."""
    corps = json.dumps({"query": requete, "variables": variables}).encode()
    req = urllib.request.Request(API, data=corps, headers={"Authorization": f"bearer {jeton}", "User-Agent": "cartes"})
    with urllib.request.urlopen(req, timeout=60) as rep:
        donnees = json.loads(rep.read())
    if donnees.get("errors"):
        raise RuntimeError(donnees["errors"])
    return donnees["data"]


Q_ANNEE = """query($login:String!,$de:DateTime!,$a:DateTime!){user(login:$login){contributionsCollection(from:$de,to:$a){
totalCommitContributions restrictedContributionsCount totalPullRequestContributions totalIssueContributions
totalPullRequestReviewContributions contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}}}"""

Q_PROFIL = """query($login:String!,$apres:String){user(login:$login){name createdAt followers{totalCount}
repositories(first:100,after:$apres,ownerAffiliations:[OWNER,COLLABORATOR,ORGANIZATION_MEMBER],isFork:false){
totalCount pageInfo{hasNextPage endCursor} nodes{stargazerCount
languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}}}}}"""


def collecter(login: str, jeton: str) -> dict:
    """Rassemble totaux, calendrier, dépôts, étoiles et langages depuis la création du compte."""
    repos, etoiles, langages, apres, profil = 0, 0, {}, None, None
    while True:
        u = graphql(Q_PROFIL, {"login": login, "apres": apres}, jeton)["user"]
        profil = profil or u
        r = u["repositories"]
        repos = r["totalCount"]
        for n in r["nodes"]:
            etoiles += n["stargazerCount"]
            for e in n["languages"]["edges"]:
                nom = e["node"]["name"]
                t, c = langages.get(nom, (0, e["node"]["color"] or DISCRET))
                langages[nom] = (t + e["size"], c)
        if not r["pageInfo"]["hasNextPage"]:
            break
        apres = r["pageInfo"]["endCursor"]
    debut = dt.datetime.fromisoformat(profil["createdAt"].replace("Z", "+00:00"))
    maintenant = dt.datetime.now(dt.timezone.utc)
    totaux = {"commits": 0, "prs": 0, "issues": 0, "revues": 0, "prive": 0}
    jours: dict[str, int] = {}
    annee_fin = maintenant
    while annee_fin > debut:
        annee_debut = max(debut, annee_fin - dt.timedelta(days=365))
        c = graphql(Q_ANNEE, {"login": login, "de": annee_debut.isoformat(), "a": annee_fin.isoformat()}, jeton)
        c = c["user"]["contributionsCollection"]
        totaux["commits"] += c["totalCommitContributions"]
        totaux["prs"] += c["totalPullRequestContributions"]
        totaux["issues"] += c["totalIssueContributions"]
        totaux["revues"] += c["totalPullRequestReviewContributions"]
        totaux["prive"] += c["restrictedContributionsCount"]
        for s in c["contributionCalendar"]["weeks"]:
            for j in s["contributionDays"]:
                jours[j["date"]] = j["contributionCount"]
        annee_fin = annee_debut
    return {
        "nom": profil["name"] or login, "login": login, "debut": debut, "suiveurs": profil["followers"]["totalCount"],
        "repos": repos, "etoiles": etoiles, "langages": langages, "totaux": totaux, "jours": jours,
    }


def demo(login: str) -> dict:
    """Données d'exemple pour tester le rendu sans jeton."""
    import random

    random.seed(3)
    aujourd_hui = dt.date.today()
    jours = {(aujourd_hui - dt.timedelta(days=i)).isoformat(): max(0, int(random.gauss(8, 9))) for i in range(900)}
    return {
        "nom": "Alex Armel Dahoui", "login": login, "debut": dt.datetime(2023, 4, 5, tzinfo=dt.timezone.utc),
        "suiveurs": 3, "repos": 171, "etoiles": 6,
        "langages": {"Python": (5_400_000, "#3572A5"), "TypeScript": (3_100_000, "#3178c6"), "Jupyter Notebook": (2_000_000, "#DA5B0B"),
                     "HTML": (900_000, "#e34c26"), "JavaScript": (400_000, "#f1e05a"), "CSS": (300_000, "#663399"), "PHP": (120_000, "#4F5D95")},
        "totaux": {"commits": 4993, "prs": 63, "issues": 1, "revues": 0, "prive": 0}, "jours": jours,
    }


# ---------------------------------------------------------------- calculs

def series(jours: dict[str, int]) -> tuple[int, int, int, str, str]:
    """Série actuelle, plus longue série, total des contributions, dates de la plus longue série."""
    dates = sorted(jours)
    meilleure, courante, debut_c, debut_m, fin_m = 0, 0, None, None, None
    for d in dates:
        if jours[d] > 0:
            courante += 1
            debut_c = debut_c or d
            if courante > meilleure:
                meilleure, debut_m, fin_m = courante, debut_c, d
        else:
            courante, debut_c = 0, None
    actuelle = 0
    for d in reversed(dates):
        if jours[d] > 0:
            actuelle += 1
        elif d != dt.date.today().isoformat():
            break
    return actuelle, meilleure, sum(jours.values()), debut_m or "", fin_m or ""


def court(n: int) -> str:
    """4993 → 5k ; 1234567 → 1,2M."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".", ",")
    if n >= 10_000:
        return f"{round(n / 1000)}k"
    return f"{n:,}".replace(",", " ")


def date_courte(iso: str) -> str:
    """2024-08-26 → 26 Aug 2024."""
    return dt.date.fromisoformat(iso).strftime("%d %b %Y") if iso else ""


# ---------------------------------------------------------------- rendu

def svg(l: int, h: int, corps: str, titre: str) -> str:
    """Enveloppe commune : fond arrondi, dégradé de marque, police système."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{l}" height="{h}" viewBox="0 0 {l} {h}" role="img" aria-label="{escape(titre)}">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{BLEU}"/><stop offset="1" stop-color="{VIOLET}"/></linearGradient>
<radialGradient id="h" cx="0.9" cy="0" r="0.8"><stop offset="0" stop-color="{BLEU}" stop-opacity="0.22"/><stop offset="1" stop-color="{BLEU}" stop-opacity="0"/></radialGradient></defs>
<style>text{{font-family:{POLICE}}} .t{{fill:{TEXTE};font-weight:700}} .d{{fill:{DISCRET};font-weight:500}}
.a{{animation:f .8s ease-out both}} @keyframes f{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:none}}}}</style>
<rect x="0.5" y="0.5" width="{l - 1}" height="{h - 1}" rx="16" fill="{CARTE}" stroke="{BORD}"/>
<rect x="0.5" y="0.5" width="{l - 1}" height="{h - 1}" rx="16" fill="url(#h)"/>
{corps}</svg>"""


def carte_stats(d: dict) -> str:
    """Totaux : contributions, commits, PR, dépôts, étoiles, années."""
    annees = max(1, dt.datetime.now(dt.timezone.utc).year - d["debut"].year)
    an_dernier = sum(v for k, v in d["jours"].items() if k >= (dt.date.today() - dt.timedelta(days=365)).isoformat())
    lignes = [("Contributions (last year)", an_dernier), ("Total commits", d["totaux"]["commits"]),
              ("Pull requests", d["totaux"]["prs"]), ("Repositories", d["repos"]), ("Stars earned", d["etoiles"])]
    corps = f'<text x="28" y="44" class="t" font-size="18">GitHub stats</text><rect x="28" y="54" width="44" height="3" rx="1.5" fill="url(#g)"/>'
    for i, (lib, val) in enumerate(lignes):
        y = 88 + i * 24
        corps += f'<g class="a" style="animation-delay:{i * 0.08:.2f}s"><text x="28" y="{y}" class="d" font-size="13">{lib}</text>'
        corps += f'<text x="300" y="{y}" class="t" font-size="13" text-anchor="end">{court(val)}</text></g>'
    corps += f'<circle cx="400" cy="112" r="50" fill="none" stroke="{BORD}" stroke-width="8"/>'
    corps += f'<circle cx="400" cy="112" r="50" fill="none" stroke="url(#g)" stroke-width="8" stroke-linecap="round" stroke-dasharray="250 314" transform="rotate(-90 400 112)"/>'
    corps += f'<text x="400" y="108" class="t" font-size="24" text-anchor="middle">{annees}+</text>'
    corps += f'<text x="400" y="128" class="d" font-size="11" text-anchor="middle">years coding</text>'
    return svg(495, 220, corps, "GitHub stats")


def carte_serie(d: dict) -> str:
    """Série actuelle, plus longue série, total."""
    actuelle, meilleure, total, debut_m, fin_m = series(d["jours"])
    depuis = date_courte(min(d["jours"])) if d["jours"] else ""
    colonnes = [(court(total), "Total contributions", f"{depuis} – today"),
                (str(actuelle), "Current streak", "days in a row"),
                (str(meilleure), "Longest streak", f"{date_courte(debut_m)} – {date_courte(fin_m)}")]
    corps = ""
    for i, (val, lib, sous) in enumerate(colonnes):
        x = 82 + i * 165
        if i == 1:
            corps += f'<circle cx="{x}" cy="92" r="42" fill="none" stroke="url(#g)" stroke-width="6"/>'
            corps += f'<path d="M{x - 6} 44 q6 -14 12 0 q-6 -4 -12 0z" fill="{VIOLET}"/>'
        corps += f'<g class="a" style="animation-delay:{i * 0.1:.2f}s"><text x="{x}" y="102" class="t" font-size="{30 if i == 1 else 26}" text-anchor="middle">{val}</text>'
        corps += f'<text x="{x}" y="160" class="t" font-size="13" text-anchor="middle">{lib}</text>'
        corps += f'<text x="{x}" y="180" class="d" font-size="10.5" text-anchor="middle">{escape(sous)}</text></g>'
    corps += f'<line x1="165" y1="40" x2="165" y2="185" stroke="{BORD}"/><line x1="330" y1="40" x2="330" y2="185" stroke="{BORD}"/>'
    return svg(495, 220, corps, "Contribution streak")


def carte_langages(d: dict) -> str:
    """Barre empilée et légende des 8 langages principaux (taille du code, dépôts privés compris)."""
    tries = sorted(d["langages"].items(), key=lambda kv: -kv[1][0])[:8]
    total = sum(t for _, (t, _) in tries) or 1
    corps = f'<text x="28" y="44" class="t" font-size="18">Most used languages</text><rect x="28" y="54" width="44" height="3" rx="1.5" fill="url(#g)"/>'
    corps += '<clipPath id="b"><rect x="28" y="76" width="439" height="12" rx="6"/></clipPath><g clip-path="url(#b)">'
    x = 28.0
    for _, (t, c) in tries:
        largeur = 439 * t / total
        corps += f'<rect x="{x:.1f}" y="76" width="{largeur + 0.5:.1f}" height="12" fill="{c}"/>'
        x += largeur
    corps += "</g>"
    for i, (nom, (t, c)) in enumerate(tries):
        cx, cy = 28 + (i % 2) * 230, 118 + (i // 2) * 24
        corps += f'<g class="a" style="animation-delay:{i * 0.06:.2f}s"><circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{c}"/>'
        corps += f'<text x="{cx + 18}" y="{cy}" class="t" font-size="12.5">{escape(nom)}</text>'
        corps += f'<text x="{cx + 205}" y="{cy}" class="d" font-size="12" text-anchor="end">{100 * t / total:.1f}%</text></g>'
    return svg(495, 220, corps, "Most used languages")


PALIERS = [("SSS", 0.98), ("SS", 0.9), ("S", 0.75), ("A", 0.5), ("B", 0.25), ("C", 0.0)]


def rang(valeur: float, seuil_max: float) -> tuple[str, float]:
    """Rang et progression d'une valeur par rapport à un objectif élevé."""
    p = min(1.0, valeur / seuil_max) if seuil_max else 0.0
    return next(n for n, s in PALIERS if p >= s), p


def carte_trophees(d: dict) -> str:
    """Rangée de trophées calculés sur les vraies données."""
    _, meilleure, total, _, _ = series(d["jours"])
    annees = max(1, dt.datetime.now(dt.timezone.utc).year - d["debut"].year)
    trophees = [("Commits", d["totaux"]["commits"], 5000), ("Contributions", total, 5000), ("Repositories", d["repos"], 150),
                ("Pull requests", d["totaux"]["prs"], 100), ("Streak", meilleure, 30), ("Languages", len(d["langages"]), 20),
                ("Experience", annees, 5)]
    couleurs = {"SSS": "#FFD166", "SS": "#FFD166", "S": "#F4B740", "A": VIOLET, "B": BLEU, "C": DISCRET}
    corps = ""
    for i, (nom, val, objectif) in enumerate(trophees):
        x = 18 + i * 140
        r, p = rang(val, objectif)
        c = couleurs[r]
        corps += f'<g transform="translate({x} 18)"><g class="a" style="animation-delay:{i * 0.07:.2f}s">'
        corps += f'<rect width="128" height="124" rx="14" fill="{FOND}" stroke="{BORD}"/>'
        corps += f'<path d="M44 26 h40 v14 a20 20 0 0 1 -40 0z" fill="{c}"/><rect x="58" y="60" width="12" height="10" fill="{c}"/>'
        corps += f'<rect x="50" y="70" width="28" height="6" rx="2" fill="{c}"/>'
        corps += f'<text x="64" y="44" font-size="13" font-weight="800" fill="{FOND}" text-anchor="middle">{r}</text>'
        corps += f'<text x="64" y="94" class="t" font-size="12" text-anchor="middle">{nom}</text>'
        corps += f'<text x="64" y="107" class="d" font-size="11" text-anchor="middle">{court(val)}</text>'
        corps += f'<rect x="22" y="114" width="84" height="3" rx="1.5" fill="{BORD}"/><rect x="22" y="114" width="{84 * p:.1f}" height="3" rx="1.5" fill="url(#g)"/></g></g>'
    return svg(998, 160, corps, "GitHub trophies")


def carte_contributions(d: dict) -> str:
    """Grille des 53 dernières semaines aux couleurs de la marque."""
    aujourd_hui = dt.date.today()
    debut = aujourd_hui - dt.timedelta(days=aujourd_hui.weekday() + 1 + 52 * 7)
    valeurs = [d["jours"].get((debut + dt.timedelta(days=i)).isoformat(), 0) for i in range(53 * 7)]
    maxi = max(valeurs) or 1
    teintes = [BORD, "#22306E", "#2C3FA3", BLEU, "#7C90FF"]
    corps = f'<text x="28" y="40" class="t" font-size="18">{court(sum(valeurs))} contributions in the last year</text>'
    for i, v in enumerate(valeurs):
        jour = debut + dt.timedelta(days=i)
        if jour > aujourd_hui:
            continue
        niveau = 0 if v == 0 else min(4, 1 + int(3 * (v / maxi) ** 0.5))
        corps += f'<rect x="{28 + (i // 7) * 17.6:.1f}" y="{58 + (i % 7) * 17}" width="13.5" height="13.5" rx="3" fill="{teintes[niveau]}"/>'
    return svg(998, 210, corps, "Contributions in the last year")


def main() -> None:
    """Point d'entrée : login, préfixe des fichiers, --demo facultatif."""
    login, prefixe = sys.argv[1], sys.argv[2]
    jeton = os.environ.get("GITHUB_TOKEN", "")
    if "--demo" in sys.argv:
        d = demo(login)
    elif jeton:
        d = collecter(login, jeton)
    else:
        sys.exit("Aucun jeton : cartes non générées (jamais de données d'exemple publiées).")
    os.makedirs(os.path.dirname(prefixe) or ".", exist_ok=True)
    for nom, rendu in (("stats", carte_stats), ("serie", carte_serie), ("langages", carte_langages),
                       ("trophees", carte_trophees), ("contributions", carte_contributions)):
        with open(f"{prefixe}-{nom}.svg", "w", encoding="utf-8") as f:
            f.write(rendu(d))
    print(f"Cartes écrites pour {login} : {d['totaux']['commits']} commits, {d['repos']} dépôts.")


if __name__ == "__main__":
    main()
