# -*- coding: utf-8 -*-
"""Pays (hors France) pour le parcours International."""

import unicodedata

COUNTRIES = [
    ("FR", "France"),
    ("ZA", "Afrique du Sud"),
    ("AL", "Albanie"),
    ("DZ", "Algérie"),
    ("DE", "Allemagne"),
    ("AD", "Andorre"),
    ("AO", "Angola"),
    ("SA", "Arabie saoudite"),
    ("AR", "Argentine"),
    ("AM", "Arménie"),
    ("AU", "Australie"),
    ("AT", "Autriche"),
    ("AZ", "Azerbaïdjan"),
    ("BE", "Belgique"),
    ("BJ", "Bénin"),
    ("BY", "Biélorussie"),
    ("MM", "Birmanie"),
    ("BO", "Bolivie"),
    ("BA", "Bosnie-Herzégovine"),
    ("BW", "Botswana"),
    ("BR", "Brésil"),
    ("BG", "Bulgarie"),
    ("BF", "Burkina Faso"),
    ("BI", "Burundi"),
    ("KH", "Cambodge"),
    ("CM", "Cameroun"),
    ("CA", "Canada"),
    ("CV", "Cap-Vert"),
    ("CL", "Chili"),
    ("CN", "Chine"),
    ("CY", "Chypre"),
    ("CO", "Colombie"),
    ("KM", "Comores"),
    ("CG", "Congo"),
    ("CD", "Congo (RDC)"),
    ("KR", "Corée du Sud"),
    ("CR", "Costa Rica"),
    ("CI", "Côte d’Ivoire"),
    ("HR", "Croatie"),
    ("CU", "Cuba"),
    ("DK", "Danemark"),
    ("DJ", "Djibouti"),
    ("EG", "Égypte"),
    ("AE", "Émirats arabes unis"),
    ("EC", "Équateur"),
    ("ES", "Espagne"),
    ("EE", "Estonie"),
    ("US", "États-Unis"),
    ("ET", "Éthiopie"),
    ("FI", "Finlande"),
    ("GA", "Gabon"),
    ("GM", "Gambie"),
    ("GE", "Géorgie"),
    ("GH", "Ghana"),
    ("GR", "Grèce"),
    ("GT", "Guatemala"),
    ("GN", "Guinée"),
    ("GQ", "Guinée équatoriale"),
    ("HT", "Haïti"),
    ("HN", "Honduras"),
    ("HU", "Hongrie"),
    ("IN", "Inde"),
    ("ID", "Indonésie"),
    ("IQ", "Irak"),
    ("IR", "Iran"),
    ("IE", "Irlande"),
    ("IS", "Islande"),
    ("IL", "Israël"),
    ("IT", "Italie"),
    ("JM", "Jamaïque"),
    ("JP", "Japon"),
    ("JO", "Jordanie"),
    ("KZ", "Kazakhstan"),
    ("KE", "Kenya"),
    ("KG", "Kirghizistan"),
    ("XK", "Kosovo"),
    ("KW", "Koweït"),
    ("LA", "Laos"),
    ("LS", "Lesotho"),
    ("LV", "Lettonie"),
    ("LB", "Liban"),
    ("LR", "Liberia"),
    ("LY", "Libye"),
    ("LI", "Liechtenstein"),
    ("LT", "Lituanie"),
    ("LU", "Luxembourg"),
    ("MK", "Macédoine du Nord"),
    ("MG", "Madagascar"),
    ("MY", "Malaisie"),
    ("MW", "Malawi"),
    ("ML", "Mali"),
    ("MT", "Malte"),
    ("MA", "Maroc"),
    ("MU", "Maurice"),
    ("MR", "Mauritanie"),
    ("MX", "Mexique"),
    ("MD", "Moldavie"),
    ("MC", "Monaco"),
    ("MN", "Mongolie"),
    ("ME", "Monténégro"),
    ("MZ", "Mozambique"),
    ("NA", "Namibie"),
    ("NP", "Népal"),
    ("NI", "Nicaragua"),
    ("NE", "Niger"),
    ("NG", "Nigeria"),
    ("NO", "Norvège"),
    ("NZ", "Nouvelle-Zélande"),
    ("UG", "Ouganda"),
    ("UZ", "Ouzbékistan"),
    ("PK", "Pakistan"),
    ("PA", "Panama"),
    ("PY", "Paraguay"),
    ("NL", "Pays-Bas"),
    ("PE", "Pérou"),
    ("PH", "Philippines"),
    ("PL", "Pologne"),
    ("PT", "Portugal"),
    ("QA", "Qatar"),
    ("RO", "Roumanie"),
    ("GB", "Royaume-Uni"),
    ("RU", "Russie"),
    ("RW", "Rwanda"),
    ("SN", "Sénégal"),
    ("RS", "Serbie"),
    ("SG", "Singapour"),
    ("SK", "Slovaquie"),
    ("SI", "Slovénie"),
    ("SO", "Somalie"),
    ("SD", "Soudan"),
    ("LK", "Sri Lanka"),
    ("SE", "Suède"),
    ("CH", "Suisse"),
    ("SR", "Suriname"),
    ("SY", "Syrie"),
    ("TW", "Taïwan"),
    ("TZ", "Tanzanie"),
    ("TD", "Tchad"),
    ("CZ", "Tchéquie"),
    ("TH", "Thaïlande"),
    ("TG", "Togo"),
    ("TN", "Tunisie"),
    ("TM", "Turkménistan"),
    ("TR", "Turquie"),
    ("UA", "Ukraine"),
    ("UY", "Uruguay"),
    ("VE", "Venezuela"),
    ("VN", "Viêt Nam"),
    ("YE", "Yémen"),
    ("ZM", "Zambie"),
    ("ZW", "Zimbabwe"),
]

POPULAR = ("CH", "BE", "ES", "IT", "DE", "GB", "PT", "NL", "US", "MA", "CA", "JP", "GR", "AT", "HR")


def _fold(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().strip()


def search_countries(q):
    term = _fold(q)
    if len(term) < 2:
        return []
    hits = []
    for code, name in COUNTRIES:
        folded = _fold(name)
        words = folded.replace("-", " ").split()
        if folded.startswith(term) or any(w.startswith(term) for w in words) or term == code.lower():
            hits.append({"code": code, "name": name})
        if len(hits) >= 12:
            break
    return hits


def country_name(code):
    code = (code or "").upper()
    for item_code, name in COUNTRIES:
        if item_code == code:
            return name
    return code
