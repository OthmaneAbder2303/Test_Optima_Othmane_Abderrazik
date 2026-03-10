"""
Pipeline complet : lecture, structuration, comparaison, rapport
"""

from dataclasses import dataclass
import re


# Etape 1 : Parsing des exigences (requirements : REQ-XX) à partir du texte réglementaire

@dataclass
class Requirement:
    id: str
    text: str

def parse_requirements(text: str) -> list[Requirement]:
    """Extraction des tout les REQ-XX a partir des lignes de texte."""
    clean = re.sub(r"===.*?===", "", text, flags=re.DOTALL)
    pattern = re.compile(r"(REQ-\d{2})\s*:\s*(.+?)(?=REQ-\d{2}\s*:|$)", re.DOTALL)
    reqs = []
    for m in pattern.finditer(clean):
        req_text = " ".join(m.group(2).split())
        if req_text:
            reqs.append(Requirement(id=m.group(1).strip(), text=req_text))
    return reqs