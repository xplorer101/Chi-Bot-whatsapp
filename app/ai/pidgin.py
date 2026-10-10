import re

PIDGIN_MARKERS = {
    "dey",
    "na",
    "abeg",
    "wetin",
    "sabi",
    "don",
    "wey",
    "una",
    "chop",
    "gist",
    "oya",
    "sha",
    "sef",
    "waka",
    "fit",
}


def detect_language(text: str) -> str:
    """Cheap heuristic returning 'english', 'pidgin' or 'mixed'."""
    lowered = text.lower()
    words = re.findall(r"[a-z']+", lowered)
    if not words:
        return "english"
    hits = sum(1 for w in words if w in PIDGIN_MARKERS)
    if "how far" in lowered:
        hits += 2
    if hits == 0:
        return "english"
    if hits >= max(2, len(words) // 4):
        return "pidgin"
    return "mixed"