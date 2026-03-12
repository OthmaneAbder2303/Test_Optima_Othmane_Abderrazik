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

    for idx, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        # Ignorer les séparateurs de sections et lignes vides
        if not line or line.startswith("---") or line.startswith("==="):
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
            token_source = f"{raw_key} {value}"
        else:
            # Ligne libre (ex. note sans clé explicite)
            key          = f"ligne_{idx}"
            value        = line
            fields[key]  = value
            raw          = line
            token_source = line

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
    # Synonymes domaine : tokens REQ → tokens fiche équivalents
    SYNONYM_GROUPS: list[set[str]] = [
        {"elements", "mobiles", "dangereux", "proteges", "dispositifs",
         "enceinte", "verrouille", "carter", "capot", "barriere", "garde", "ecran"},
        {"declaration", "signe", "signee", "representant", "signataire"},
        {"notice", "instructions", "manuel", "documentation"},
        {"risques", "residuels", "dangers", "identifies"},
        {"arret", "urgence", "stop", "securite"},
        {"organisme", "notifie", "certifie", "tierce"},
    ]

    def expand(tokens: set[str]) -> set[str]:
        expanded = set(tokens)
        for group in SYNONYM_GROUPS:
            if tokens & group:          # si au moins un token du groupe est présent
                expanded |= group       # on ajoute tout le groupe
        return expanded

    expanded_req = expand(requirement_tokens)
    expanded_key = expand(set(evidence.key.split("_")))

    overlap_key   = len(expanded_req & expanded_key)
    overlap_value = len(expanded_req & evidence.tokens)
    return (2.0 * overlap_key) + overlap_value

#  3c. Détection de marqueurs

def has_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    r"""
    Détecte la présence d'un marqueur dans le texte normalisé.
    Utilise \b pour les frontières de mots et \s+ pour tolérer les variantes
    d'espacement dans les marqueurs multi-mots (ex. "en cours").
    """
    normalized = normalize_text(text)
    for phrase in phrases:
        escaped = re.escape(phrase)
        pattern = r"\b" + escaped.replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, normalized):
            return True
    return False

# Règles métiers spécifiques
def check_language_compliance(product: ProductData, merged_evidence: str) -> bool:
    markets = product.fields.get("marches_vises", "").lower()
    if not markets: return False
    lang_map = {"france": "francais", "italie": "italien", "portugal": "portugais"}
    text_norm = normalize_text(merged_evidence)
    for country, lang in lang_map.items():
        if country in markets and lang not in text_norm:
            return False
    return True

#  3d. Évaluation d'une exigence

def evaluate_requirement(
    requirement: Requirement, product: ProductData, top_n: int = 3
) -> Decision:
    """
    Évalue une exigence contre la fiche produit.
    """
    requirement_tokens = extract_keywords(requirement)

    #  1 : scorer toutes les preuves
    scored = []
    for evidence in product.evidences:
        score = score_evidence(requirement_tokens, evidence)
        if score > 0:
            scored.append((score, evidence))
    scored.sort(key=lambda item: item[0], reverse=True)

    #  2 : sélectionner les preuves les plus pertinentes
    matched: list[Evidence] = []
    if scored:
        best_score = scored[0][0]
        min_score = max(1.0, best_score - 0.5)
        matched   = [ev for score, ev in scored if score >= min_score][:top_n]

    if not matched:
        return Decision(
            requirement=requirement,
            status=Status.NON_SATISFAIT,
            reason="Aucune preuve claire n'a ete trouvee dans la fiche produit.",
        )

    merged_evidence   = " | ".join(item.raw_line for item in matched)
    evidence_hint = f"Preuve principale: {matched[0].raw_line}"

    # Règles métiers prioritaires
    if requirement.req_id == "REQ-06":
        if check_language_compliance(product, merged_evidence):
            return Decision(requirement, Status.SATISFAIT,
                            f"Notice disponible dans toutes les langues requises. {evidence_hint}")
        else:
            return Decision(requirement, Status.NON_SATISFAIT,
                            "Notice manquante dans une langue visée.",
                            "Traduire en langues visées.")
        
    if requirement.req_id == "REQ-09":
        # Termes indiquant qu'une solution de protection est en place
        protection_terms = (
            "enceinte", "verrouille", "carter", "capot",
            "barriere", "protecteur", "garde", "ecran",
        )
        # Termes indiquant que la fiche adresse le sujet (éléments mobiles)
        subject_terms = (
            "elements", "mobiles", "dangereux", "proteges", "dispositifs",
        )
        addresses_subject = has_any_phrase(merged_evidence, subject_terms)
        has_protection    = has_any_phrase(merged_evidence, protection_terms)
        is_absent         = has_any_phrase(merged_evidence, ("absent", "non", "sans", "pas"))

        if has_protection and not is_absent:
            return Decision(requirement, Status.SATISFAIT,
                            f"Dispositif de protection des éléments mobiles présent. {evidence_hint}")
        elif has_protection and is_absent:
            return Decision(requirement, Status.NON_SATISFAIT,
                            f"Dispositif de protection mentionné mais absent. {evidence_hint}")
        elif addresses_subject:
            # Le sujet est mentionné mais sans solution identifiable
            return Decision(requirement, Status.AMBIGU,
                            f"Éléments mobiles mentionnés sans preuve de protection. {evidence_hint}",
                            "Préciser le type de dispositif de protection installé.")
        else:
            return Decision(requirement, Status.NON_SATISFAIT,
                            "Aucune preuve claire n'a ete trouvee dans la fiche produit.")
            
    if requirement.req_id == "REQ-11":
        risk_high         = has_any_phrase(merged_evidence, ("eleve", "critique", "haut"))
        body_absent       = has_any_phrase(merged_evidence, ("absent", "aucun", "sans"))
        has_notified_body = has_any_phrase(merged_evidence, ("notifie", "certifie")) and not body_absent

        if not risk_high:
            return Decision(requirement, Status.SATISFAIT,
                            f"Intervention d'un organisme notifié non requise. {evidence_hint}")
        if has_notified_body:
            return Decision(requirement, Status.SATISFAIT,
                            f"Organisme notifié présent pour machine à risque élevé. {evidence_hint}")
        if body_absent:
            return Decision(requirement, Status.NON_SATISFAIT,
                            f"Non-conformite detectee. {evidence_hint}")
        return Decision(requirement, Status.AMBIGU,
                        f"Risque élevé détecté mais statut de l'organisme notifié non vérifiable. {evidence_hint}",
                        "Confirmer l'intervention d'un organisme notifié.")

    # Arbre de décision général
    has_positive      = has_any_phrase(merged_evidence, POSITIVE_MARKERS)
    has_hard_negative = has_any_phrase(merged_evidence, HARD_NEGATIVE_MARKERS)
    has_soft_negative = has_any_phrase(merged_evidence, SOFT_NEGATIVE_MARKERS)
    has_uncertain     = has_any_phrase(merged_evidence, UNCERTAIN_MARKERS)
    missing_refs      = sorted(extract_reference_numbers(requirement.description) - extract_reference_numbers(merged_evidence))

    if has_positive and not (has_hard_negative or has_soft_negative or has_uncertain or missing_refs):
        return Decision(requirement, Status.SATISFAIT, f"Exigence couverte. {evidence_hint}")
    
    if has_hard_negative and not has_positive:
        return Decision(requirement, Status.NON_SATISFAIT, f"Non-conformite detectee. {evidence_hint}")

    return Decision(requirement, Status.AMBIGU, f"Information insuffisante. {evidence_hint}", "Completer la preuve.")


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