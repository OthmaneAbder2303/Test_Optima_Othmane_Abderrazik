"""
Pipeline complet : lecture, structuration, comparaison, rapport
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
import unicodedata


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
    "non", "aucun", "aucune", "absent", "absente", "sans", "manquant",
    "manquante", "inexistant", "inexistante",
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
    return (2.0 * overlap_key) + overlap_value


#  3c. Détection de marqueurs

def has_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    """
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

#  3d. Évaluation d'une exigence

def evaluate_requirement(
    requirement: Requirement, product: ProductData, top_n: int = 3
) -> Decision:
    """
    Évalue une exigence contre la fiche produit.

    Pipeline de décision :
      1. Score toutes les preuves (lexical).
      2. Sélectionne les top-n preuves proches du meilleur score (fenêtre fixe).
      3. Fusionne les preuves et détecte les marqueurs positifs/négatifs/incertains.
      4. Vérifie la présence des références normatives requises.
      5. Retourne SATISFAIT, NON SATISFAIT ou AMBIGU avec justification.

    AMBIGU est retourné dès qu'une information est présente mais insuffisante
    pour conclure (incertitude, négation partielle, référence manquante, etc.).
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
        # Fenêtre fixe : on garde les preuves dans un écart de 0.5 du meilleur
        min_score = max(1.0, best_score - 0.5)
        matched   = [ev for score, ev in scored if score >= min_score][:top_n]

    #  3 : aucune preuve trouvée → NON SATISFAIT immédiat
    if not matched:
        return Decision(
            requirement=requirement,
            status=Status.NON_SATISFAIT,
            reason="Aucune preuve claire n'a ete trouvee dans la fiche produit pour cette exigence.",
            missing_info="Ajouter une ligne explicite dans la fiche produit couvrant cette obligation.",
        )

    # 4 : détecter les marqueurs dans les preuves fusionnées
    merged_evidence   = " | ".join(item.raw_line for item in matched)
    has_positive      = has_any_phrase(merged_evidence, POSITIVE_MARKERS)
    has_hard_negative = has_any_phrase(merged_evidence, HARD_NEGATIVE_MARKERS)
    has_soft_negative = has_any_phrase(merged_evidence, SOFT_NEGATIVE_MARKERS)
    has_uncertain     = has_any_phrase(merged_evidence, UNCERTAIN_MARKERS)

    # 5 : vérifier les références normatives
    needed_refs  = extract_reference_numbers(requirement.description)
    seen_refs    = extract_reference_numbers(merged_evidence)
    missing_refs = sorted(needed_refs - seen_refs)

    evidence_hint = f"Preuve principale: {matched[0].raw_line}"

    # 6 : arbre de décision
    # Cas 1 : signal positif clair, aucun signal négatif ou incertain → SATISFAIT
    if (has_positive and not has_hard_negative
            and not has_soft_negative and not has_uncertain
            and not missing_refs):
        return Decision(requirement, Status.SATISFAIT, f"Exigence couverte. {evidence_hint}")

    # Cas 2 : négation explicite sans aucun positif → NON SATISFAIT
    if has_hard_negative and not has_positive:
        return Decision(
            requirement,
            Status.NON_SATISFAIT,
            f"Les preuves pointent une non-conformite explicite. {evidence_hint}",
        )

    # Cas 3 : positif mais référence normative absente → AMBIGU
    if has_positive and missing_refs:
        missing = ", ".join(missing_refs)
        return Decision(
            requirement,
            Status.AMBIGU,
            f"Conformite probable mais reference normative manquante ({missing}). {evidence_hint}",
            missing_info=f"Ajouter la reference explicite: {missing}.",
        )

    # Cas 4 : incertitude, partiel, ou contradiction → AMBIGU
    if has_uncertain or has_soft_negative or (has_positive and has_hard_negative):
        return Decision(
            requirement,
            Status.AMBIGU,
            f"Information presente mais insuffisante ou partiellement contradictoire. {evidence_hint}",
            missing_info="Fournir une preuve explicite, complete et datee de conformite.",
        )

    # Cas 5 : indices présents mais non concluants → AMBIGU par défaut
    return Decision(
        requirement,
        Status.AMBIGU,
        f"Des indices existent mais ne permettent pas de conclure. {evidence_hint}",
        missing_info="Completer la fiche avec un statut clair (oui/non), preuve et reference associee.",
    )


