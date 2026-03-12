"""
Pipeline complet : lecture, structuration, comparaison, rapport
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
import unicodedata
import argparse


# ─────────────────────────────────────────────────────────────────────────────
# Constantes linguistiques (partagées par les 3 étapes)
# ─────────────────────────────────────────────────────────────────────────────

STOPWORDS = {
    "a", "au", "aux", "avec", "ce", "ces", "chaque", "dans", "de", "des",
    "doit", "du", "en", "et", "etre", "la", "le", "les", "par", "pas",
    "pour", "sur", "un", "une",
}

POSITIVE_MARKERS = (
    "oui", "present", "presente", "complet", "complete", "conforme",
    "certifie", "certifiee", "valide", "validee", "signe", "signee",
    "appose", "apposee", "realise", "realisee", "effectue", "effectuee",
    "verrouille", "verrouilee", "enceinte",
)

HARD_NEGATIVE_MARKERS = (
    "non", "aucun", "aucune", "mais", "absent", "absente", "sans", "manquant",
    "manquante", "inexistant", "inexistante", "standard", "basse",
)

SOFT_NEGATIVE_MARKERS = (
    "partiel", "partielle", "incomplet", "incomplete", "limite", "limitee",
    "uniquement",
)

UNCERTAIN_MARKERS = (
    "en cours", "prevu", "prevue", "a confirmer", "a valider",
    "non precise", "non precisee", "non verifiable", "en attente",
)


# ─────────────────────────────────────────────────────────────────────────────
# Structures de données (utilisées dans les 3 étapes)
# ─────────────────────────────────────────────────────────────────────────────

class Status(str, Enum):
    SATISFAIT     = "SATISFAIT"
    NON_SATISFAIT = "NON SATISFAIT"
    AMBIGU        = "AMBIGU"

@dataclass(frozen=True)
class Requirement:
    """Représente une exigence réglementaire extraite (Étape 1)."""
    req_id: str        # identifiant normalisé, ex. "REQ-01"
    description: str   # texte de l'exigence, espaces normalisés

@dataclass(frozen=True)
class Evidence:
    """Représente une information extraite de la fiche produit (Étape 2)."""
    key: str          # clé normalisée en snake_case, ex. "declaration_ce"
    value: str        # valeur brute, ex. "EN COURS, signature prevue avant livraison"
    raw_line: str     # ligne reconstituée pour l'affichage dans le rapport
    tokens: set[str]  # tokens du couple clé+valeur pour le scoring lexical

@dataclass
class ProductData:
    """Fiche produit structurée (Étape 2)."""
    fields: dict[str, str]     # accès rapide par clé normalisée
    evidences: list[Evidence]  # liste ordonnée pour le scoring

@dataclass(frozen=True)
class Decision:
    """Résultat de l'évaluation d'une exigence (Étape 3)."""
    requirement: Requirement
    status: Status
    reason: str
    missing_info: str | None = None  # action corrective suggérée si AMBIGU/NON SATISFAIT



# ─────────────────────────────────────────────────────────────────────────────
# Utilitaires de normalisation (partagés par les 3 étapes)
# ─────────────────────────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """Supprime les accents et met en minuscules."""
    deaccented = "".join(
        char for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    return deaccented.lower()

def normalize_key(key: str) -> str:
    """Convertit une clé brute en snake_case sans accents ni caractères spéciaux."""
    normalized = re.sub(r"[^a-z0-9]+", "_", normalize_text(key))
    return normalized.strip("_")

def tokenize(text: str) -> set[str]:
    """Extrait les tokens alphanumériques de longueur ≥ 2."""
    return set(re.findall(r"[a-z0-9]{2,}", normalize_text(text)))

def normalize_req_id(raw_req_id: str) -> str:
    """Normalise un identifiant REQ en format 'REQ-XX'."""
    # Extrait uniquement les chiffres, puis reconstruit l'ID
    num = re.sub(r"\D", "", raw_req_id)
    return f"REQ-{num.zfill(2)}"


# ═════════════════════════════════════════════════════════════════════════════
# ÉTAPE 1 — Structurer les exigences
# Lecture du texte réglementaire et extraction de chaque exigence REQ-XX
# sous forme d'objets Requirement (req_id + description).
# ═════════════════════════════════════════════════════════════════════════════

def parse_requirements(text: str) -> list[Requirement]:
    """
    Extrait les exigences du texte réglementaire.

    Stratégie principale (regex lookahead) :
        Capture tout le texte entre deux identifiants REQ consécutifs.
        Robuste aux sauts de ligne et aux variantes de formatage (REQ-01, REQ 01, REQ_01).

    Stratégie fallback (numérotation automatique) :
        Si aucun identifiant REQ n'est détecté, chaque ligne non vide devient
        une exigence numérotée automatiquement REQ-01, REQ-02, etc.
        Utile pour des textes réglementaires sans format structuré.
    """
    # Nettoyage global des balises parasites avant tout traitement
    clean_text = re.sub(r"===.*?===", "", text, flags=re.DOTALL)
    clean_text = re.sub(r"---.*?---", "", clean_text, flags=re.DOTALL)

    # Tentative de parsing par identifiant REQ
    req_pattern = re.compile(
        r"(REQ[-_ ]?[A-Z0-9][A-Z0-9-]*)\s*[:\-]\s*(.+?)"
        r"(?=(?:\n\s*REQ[-_ ]?[A-Z0-9][A-Z0-9-]*\s*[:\-])|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    
    parsed = [
        Requirement(
            req_id=normalize_req_id(req_id),
            description=" ".join(description.split()).strip(),
        )
        for req_id, description in req_pattern.findall(clean_text)
    ]
    
    if parsed:
        return parsed

    # Fallback : numérotation automatique ligne par ligne
    fallback: list[Requirement] = []
    for raw_line in clean_text.splitlines():
        line = raw_line.strip()
        # Ignorer les lignes vides
        if not line:
            continue
        # Supprimer les puces et numéros de liste éventuels
        cleaned = re.sub(r"^[-*]\s+", "", line)
        cleaned = re.sub(r"^\d+[.)]\s+", "", cleaned)
        if len(cleaned) < 8:
            continue
        req_id = f"REQ-{len(fallback) + 1:02d}"
        fallback.append(Requirement(req_id=req_id, description=cleaned))

    if not parsed and not fallback:
        raise ValueError(
            "Aucune exigence exploitable n'a ete detectee dans le texte reglementaire."
        )
    return fallback

# ═════════════════════════════════════════════════════════════════════════════
# ÉTAPE 2 — Analyser la fiche produit
# Lecture de la fiche produit et extraction des informations sous forme
# d'objets Evidence (clé normalisée, valeur brute, tokens pour comparaison).
# ═════════════════════════════════════════════════════════════════════════════

def parse_product_sheet(text: str) -> ProductData:
    """
    Parse la fiche produit ligne par ligne.

    Chaque ligne "Clé : Valeur" produit une Evidence avec :
      - key    : clé normalisée en snake_case (ex. "declaration_ce")
                 → permet la comparaison même si le vocabulaire diffère
      - value  : valeur brute conservée pour la détection de marqueurs
      - tokens : union des tokens clé+valeur pour le scoring lexical

    Les lignes sans ":" sont indexées par leur numéro de ligne (notes libres).
    Les clés dupliquées sont concaténées avec " | " pour ne rien perdre.
    """
    fields: dict[str, str] = {}
    evidences: list[Evidence] = []
    current_section = ""

    for idx, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        # Ignorer les séparateurs de sections === et lignes vides
        if not line or line.startswith("==="):
            continue

        # Détecter les titres de section et les mémoriser
        if line.startswith("---"):
            current_section = normalize_key(line.strip("-").strip())
            continue

        if ":" in line:
            # Ligne structurée : séparer clé et valeur sur le premier ":"
            raw_key, raw_value = line.split(":", 1)
            key   = normalize_key(raw_key)
            value = raw_value.strip()
            # Concaténer si la clé apparaît plusieurs fois
            existing    = fields.get(key)
            fields[key] = f"{existing} | {value}" if existing else value
            raw          = f"{raw_key.strip()}: {value}"
            token_source = f"{current_section} {raw_key} {value}"
        else:
            # Ligne libre (ex. note sans clé explicite)
            key          = f"ligne_{idx}"
            value        = line
            fields[key]  = value
            raw          = line
            token_source = f"{current_section} {line}"

        evidences.append(
            Evidence(key=key, value=value, raw_line=raw, tokens=tokenize(token_source))
        )

    return ProductData(fields=fields, evidences=evidences)


# ═════════════════════════════════════════════════════════════════════════════
# ÉTAPE 3 — Comparer et produire le rapport
# Pour chaque exigence : scoring des preuves, détection de marqueurs,
# verdict SATISFAIT / NON SATISFAIT / AMBIGU.
# ═════════════════════════════════════════════════════════════════════════════

#  3a. Extraction de mots-clés

def extract_keywords(requirement: Requirement) -> set[str]:
    """
    Extrait les tokens significatifs de l'exigence.
    Filtre les stopwords et les tokens trop courts (≤ 2 caractères).
    Si tous les tokens sont filtrés, conserve l'ensemble complet (sécurité).
    """
    tokens   = tokenize(requirement.description)
    filtered = {token for token in tokens if token not in STOPWORDS and len(token) > 2}
    return filtered or tokens

def extract_reference_numbers(text: str) -> set[str]:
    """
    Extrait les références normatives numériques (3 à 6 chiffres).
    Ex. "EN 13850" → {"13850"}.
    Utilisé pour détecter les cas où une norme est exigée mais non citée.
    """
    return set(re.findall(r"\b\d{3,6}\b", normalize_text(text)))


#  3b. Scoring lexical

def score_evidence(requirement_tokens: set[str], evidence: Evidence) -> float:
    """
    Score lexical d'une preuve vis-à-vis d'une exigence.

    Formule : (2 × overlap_clé) + overlap_valeur
      - La clé est pondérée ×2 car elle identifie le champ sémantique.
      - overlap_valeur capte les termes partagés dans le contenu de la preuve.

    Ce score brut sert à classer les preuves par pertinence avant la décision.
    """
    key_tokens    = set(evidence.key.split("_"))
    overlap_key   = len(requirement_tokens & key_tokens)
    overlap_value = len(requirement_tokens & evidence.tokens)
    partial_bonus = sum(
        0.5 for req_tok in requirement_tokens
        for ev_tok in evidence.tokens | key_tokens
        if req_tok in ev_tok or ev_tok in req_tok
    )
    
    return (2.0 * overlap_key) + overlap_value + partial_bonus

#  3c. Détection de marqueurs

def has_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    """
    Détecte la présence d'un marqueur dans le texte normalisé.
    """
    normalized = normalize_text(text)
    for phrase in phrases:
        escaped = re.escape(phrase)
        pattern = r"\b" + escaped.replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, normalized):
            return True
    return False


# Règles métiers spécifiques
def get_target_markets(product: ProductData) -> str:
    """Extrait les pays présents dans toute la fiche produit, indépendamment de la clé."""
    full_content = " ".join(product.fields.values()).lower()
    known_countries = {"france", "italie", "portugal", "espagne", "allemagne", "belgique"}
    return " ".join([c for c in known_countries if c in full_content])

def check_language_compliance(product: ProductData, merged_evidence: str) -> bool:
    """Vérifie si la langue requise est présente et non infirmée."""
    markets_raw = get_target_markets(product)
    if not markets_raw: return True 

    reference_lang = {
        "france": "francais", "italie": "italien", "portugal": "portugais",
        "espagne": "espagnol", "allemagne": "allemand", "belgique": "francais"
    }
    
    text_norm = normalize_text(merged_evidence)
    
    for country, lang in reference_lang.items():
        if country in markets_raw:
            # On cherche la langue. 
            # On vérifie qu'elle n'est pas suivie de "non", "absent", etc.
            # On crée un pattern pour détecter la langue et les mots négatifs proches
            if lang not in text_norm:
                return False
            
            # Vérifier si la langue est invalidée dans la même zone
            # On cherche des marqueurs négatifs juste après la langue
            negative_indicators = ["non", "pas", "absent", "manquant"]
            for neg in negative_indicators:
                if f"{lang} {neg}" in text_norm or f"{neg} {lang}" in text_norm:
                    return False
                    
    return True

#  3d. Évaluation d'une exigence
def evaluate_requirement(
    requirement: Requirement, product: ProductData, top_n: int = 3
) -> Decision:
    """Évalue une exigence contre la fiche produit avec règles métiers."""
    requirement_tokens = extract_keywords(requirement)

    scored = sorted([(score_evidence(requirement_tokens, ev), ev) 
                     for ev in product.evidences if score_evidence(requirement_tokens, ev) > 0], 
                    key=lambda item: item[0], reverse=True)

    matched = [ev for score, ev in scored if score >= max(1.0, scored[0][0] - 0.5)][:top_n] if scored else []

    if not matched:
        return Decision(requirement, Status.NON_SATISFAIT, "Aucune preuve claire trouvée.")

    #merged_evidence = " | ".join(item.raw_line for item in matched)
    merged_evidence = " | ".join(product.fields.values())
    evidence_hint = f"Preuve principale: {matched[0].raw_line}"
    evidence_text = normalize_text(merged_evidence)
    
    # REQ-06 : Vérification linguistique dynamique
    if requirement.req_id == "REQ-06":
        if check_language_compliance(product, merged_evidence):
            # AJOUT : Retour immédiat si conforme
            return Decision(requirement, Status.SATISFAIT, f"Conformité linguistique vérifiée. {evidence_hint}")
        else:
            return Decision(requirement, Status.NON_SATISFAIT, "Notice manquante dans une langue d'un pays visé.", "Traduire la notice.")
        
    # REQ-11 : Gestion générique des niveaux de risque
    if requirement.req_id == "REQ-11":
        risk_levels = {"faible": 1, "standard": 1, "moyen": 2, "eleve": 3, "critique": 3}
        found_level = next((lvl for lvl in risk_levels if lvl in evidence_text), None)
        
        if found_level:
            if risk_levels[found_level] >= 3:
                # On vérifie la présence de l'organisme tout en excluant le cas "sans"
                has_organism = ("organisme" in evidence_text or "notifie" in evidence_text)
                is_negative = any(m in evidence_text for m in ["sans", "absent", "manquant", "non conforme"])
                
                if has_organism and not is_negative:
                    return Decision(requirement, Status.SATISFAIT, f"Risque {found_level} : organisme notifié identifié. {evidence_hint}")
                else:
                    return Decision(requirement, Status.NON_SATISFAIT, f"Risque {found_level} : organisme notifié manquant ou explicitement absent.")
            
            return Decision(requirement, Status.SATISFAIT, f"Risque {found_level} : intervention organisme non requise.")
        
    #  ARBRE DE DÉCISION GÉNÉRAL
    has_positive = has_any_phrase(merged_evidence, POSITIVE_MARKERS)
    has_hard_negative = has_any_phrase(merged_evidence, HARD_NEGATIVE_MARKERS)
    has_soft_negative = has_any_phrase(merged_evidence, SOFT_NEGATIVE_MARKERS)
    has_uncertain = has_any_phrase(merged_evidence, UNCERTAIN_MARKERS)
    missing_refs = sorted(extract_reference_numbers(requirement.description) - extract_reference_numbers(merged_evidence))

    if has_positive and not (has_hard_negative or has_soft_negative or has_uncertain or missing_refs):
        return Decision(requirement, Status.SATISFAIT, f"Exigence couverte. {evidence_hint}")
    
    if has_hard_negative and not has_positive:
        return Decision(requirement, Status.NON_SATISFAIT, f"Non-conformité explicite. {evidence_hint}")

    return Decision(requirement, Status.AMBIGU, f"Information insuffisante. {evidence_hint}", "Compléter la preuve ou référence.")


#  3e. Orchestration et Rapport (Maintenus) 

def run_audit(requirements: list[Requirement], product: ProductData) -> list[Decision]:
    return [evaluate_requirement(requirement, product) for requirement in requirements]


#  3f. Mise en forme du rapport 

def group_by_status(decisions: list[Decision]) -> dict[Status, list[Decision]]:
    """Regroupe les décisions par statut pour l'affichage du rapport."""
    groups: dict[Status, list[Decision]] = {
        Status.SATISFAIT:     [],
        Status.NON_SATISFAIT: [],
        Status.AMBIGU:        [],
    }
    for decision in decisions:
        groups[decision.status].append(decision)
    return groups


def format_group(
    title: str, decisions: list[Decision], include_missing_info: bool = False
) -> list[str]:
    """Formate une section du rapport pour un statut donné."""
    lines = [title]
    if not decisions:
        lines.append("- Aucun")
        return lines
    for decision in decisions:
        lines.append(
            f"- [{decision.requirement.req_id}] "
            f"{decision.requirement.description} -> {decision.reason}"
        )
        if include_missing_info and decision.missing_info:
            lines.append(f"  Manque pour conclure: {decision.missing_info}")
    return lines


def build_report(decisions: list[Decision]) -> str:
    """
    Construit le rapport final.
    Ordre d'affichage : NON SATISFAIT → AMBIGU (avec actions correctives) → SATISFAIT.
    """
    groups = group_by_status(decisions)
    total  = len(decisions)
    lines  = [
        "RAPPORT D'AUDIT",
        f"Satisfait      : {len(groups[Status.SATISFAIT])} / {total}",
        f"Non satisfait  : {len(groups[Status.NON_SATISFAIT])} / {total}",
        f"Ambigu         : {len(groups[Status.AMBIGU])} / {total}",
        "",
    ]
    lines.extend(format_group("NON SATISFAIT :", groups[Status.NON_SATISFAIT]))
    lines.append("")
    lines.extend(
        format_group(
            "AMBIGU (information presente mais insuffisante) :",
            groups[Status.AMBIGU],
            include_missing_info=True,
        )
    )
    lines.append("")
    lines.extend(format_group("SATISFAIT :", groups[Status.SATISFAIT]))
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Entrée — lecture des fichiers et lancement de l'audit
# ─────────────────────────────────────────────────────────────────────────────

def read_file(path: str) -> str:
    """Lit un fichier texte encodé en UTF-8."""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit de conformite generique (reglementation vs fiche produit)."
    )
    parser.add_argument(
        "--req", dest="regulatory_file", required=True,
        help="Chemin vers le texte des exigences (ex. data/texte_reglementaire.txt).",
    )
    parser.add_argument(
        "--prod", dest="product_file", required=True,
        help="Chemin vers la fiche produit (ex. data/fiche_produit.txt).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Étape 1 - Structurer les exigences
    regulatory_text = read_file(args.regulatory_file)
    requirements    = parse_requirements(regulatory_text)

    # Étape 2 - Analyser la fiche produit
    product_text = read_file(args.product_file)
    product      = parse_product_sheet(product_text)

    # Étape 3 - Comparer et produire le rapport
    decisions = run_audit(requirements, product)
    print(build_report(decisions))


if __name__ == "__main__":
    main()
