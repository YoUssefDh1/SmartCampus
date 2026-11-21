import re
from dataclasses import dataclass

ARABIC_SCRIPT = re.compile(r"[\u0600-\u06ff]")
TOKENS = re.compile(r"[\w']+", re.UNICODE)

TUNISIAN_MARKERS = {
    "3andi", "chneya", "chnoua", "chnowa", "chnouma", "fama",
    "kifech", "mta3", "ma3andich", "najm", "najem", "nheb", "n7eb",
    "tansahni", "win",
}
FRENCH_MARKERS = {
    "admission", "bac", "bonjour", "combien", "comment", "conditions", "conseiller",
    "école", "etudes", "études", "formation", "formations", "frais",
    "informatique", "je", "j'aime", "les", "meilleures", "peux",
    "pourquoi", "quelle", "quelles", "quels", "qu'est", "recommande",
    "salut", "sont", "tu", "une", "vous", "veux", "être", "étudier",
}
CONFIDENT_THRESHOLD = 0.8


@dataclass(frozen=True)
class LanguageDetection:
    language: str
    confidence: float


def detect_language(text: str) -> LanguageDetection:
    tokens = set(TOKENS.findall(text.lower()))
    arabic_chars = len(ARABIC_SCRIPT.findall(text))
    latin_chars = sum(char.isascii() and char.isalpha() for char in text)
    tunisian_hits = tokens & TUNISIAN_MARKERS
    french_hits = tokens & FRENCH_MARKERS

    if arabic_chars:
        if latin_chars and french_hits:
            return LanguageDetection("mixed", 0.85)
        return LanguageDetection("tn-arabic", 0.95)
    if tunisian_hits and french_hits:
        return LanguageDetection("mixed", 0.85)
    if tunisian_hits:
        return LanguageDetection("arabizi", 0.85)
    if len(french_hits) >= 2 or french_hits & {"bonjour", "salut"}:
        return LanguageDetection("fr", 0.85)
    return LanguageDetection("unknown", 0.0)
