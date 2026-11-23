"""Extraction déterministe des signaux de profil visiteur (SA-26).

Complète `agents/language.py` : on repère dans le texte brut le niveau d'études,
les domaines d'intérêt et les institutions citées, sans appel LLM.
"""
import re

TOKENS = re.compile(r"\w+", re.UNICODE)  # l'apostrophe sépare : « l'informatique » -> {l, informatique}

# Les valeurs détectées par agents/language.py ne recouvrent pas le domaine SQL
# `chat_language` ('fr', 'tn', 'tn-arabizi') : mixed/unknown n'y ont pas d'équivalent.
_LANGUAGE_TO_CHAT_LANGUAGE = {
    "fr": "fr",
    "tn-arabic": "tn",
    "arabizi": "tn-arabizi",
}

EDUCATION_LEVELS: dict[str, tuple[str, ...]] = {
    "Baccalauréat": ("bac", "baccalauréat", "baccalaureat", "lycée", "lycee", "terminale", "secondaire"),
    "Licence": ("licence", "license", "bachlor", "bachelor"),
    "Master": ("master", "mastère", "mastere", "m2", "m1"),
    "Cycle Ingénieur": ("ingénieur", "ingenieur", "prépa", "prepa", "préparatoire", "preparatoire"),
}

INTERESTS: dict[str, tuple[str, ...]] = {
    "Informatique": ("informatique", "logiciel", "développement", "developpement", "code", "data", "ia", "cyber", "réseau", "reseau"),
    "Gestion": ("gestion", "management", "business", "finance", "comptabilité", "comptabilite", "marketing", "économie", "economie"),
    "Génie Civil": ("civil", "construction", "btp", "bâtiment", "batiment", "travaux"),
    "Génie Industriel": ("industriel", "industrie", "mécanique", "mecanique", "électromécanique", "electromecanique", "robotique"),
}

INSTITUTIONS: dict[str, tuple[str, ...]] = {
    "IIT": ("iit", "institut international de technologie"),
    "ISB": ("isb", "international school of business"),
}


def to_chat_language(detected: str) -> str | None:
    """Traduit une langue détectée en valeur du domaine SQL `chat_language`."""
    return _LANGUAGE_TO_CHAT_LANGUAGE.get(detected)


def _matches(tokens: set[str], haystack: str, keywords: tuple[str, ...]) -> bool:
    for keyword in keywords:
        if " " in keyword:
            if keyword in haystack:
                return True
        elif keyword in tokens:
            return True
    return False


def extract_profile_signals(text: str) -> dict:
    """Retourne les attributs repérés dans un message : {education_level?, interests[], target_institutions[]}."""
    haystack = text.lower()
    tokens = set(TOKENS.findall(haystack))

    signals: dict = {"interests": [], "target_institutions": []}
    for level, keywords in EDUCATION_LEVELS.items():
        if _matches(tokens, haystack, keywords):
            signals["education_level"] = level
            break
    for interest, keywords in INTERESTS.items():
        if _matches(tokens, haystack, keywords):
            signals["interests"].append(interest)
    for institution, keywords in INSTITUTIONS.items():
        if _matches(tokens, haystack, keywords):
            signals["target_institutions"].append(institution)
    return signals
