"""
TESTS UNITAIRES — ÉVALUATION ET DÉCISION (Audit de Conformité)

Ce module valide la logique de comparaison entre les exigences et la fiche produit :
1. Scoring lexical (score_evidence) : pondération des clés et tokens.
2. Détection de marqueurs (has_any_phrase) : identification des termes de conformité.
3. Règles métiers (evaluate_requirement) :
   - REQ-06 : Conformité linguistique selon les marchés.
   - REQ-11 : Analyse des risques et organismes notifiés.
   - Cas généraux : SATISFAIT, NON SATISFAIT, AMBIGU.
"""

import pytest
from audit import (
    Requirement, parse_product_sheet, evaluate_requirement, 
    score_evidence, Evidence, Status, tokenize, has_any_phrase,
    POSITIVE_MARKERS, HARD_NEGATIVE_MARKERS
)

class TestScoringLogic:

    def test_score_evidence_priorise_cle(self):
        """Vérifie que le matching sur la clé rapporte plus que sur la valeur."""
        req_tokens = {"marquage", "ce"}
        # Evidence avec "marquage" dans la clé
        ev1 = Evidence(key="marquage_ce", value="oui", raw_line="Marquage CE: oui", tokens={"oui", "marquage", "ce"})
        # Evidence avec "marquage" uniquement dans la valeur
        ev2 = Evidence(key="status", value="marquage effectue", raw_line="Status: marquage", tokens={"status", "marquage"})
        
        assert score_evidence(req_tokens, ev1) > score_evidence(req_tokens, ev2)

    def test_has_any_phrase_exact_match(self):
        """Vérifie la détection robuste des marqueurs avec limites de mots."""
        text = "Le document est present et valide"
        assert has_any_phrase(text, POSITIVE_MARKERS) is True
        assert has_any_phrase(text, ("absent",)) is False
        # Test limite de mot (ne doit pas matcher 'present' dans 'representant')
        assert has_any_phrase("representant legal", ("present",)) is False


class TestBusinessRules:

    @pytest.fixture
    def req_langue(self):
        return Requirement("REQ-06", "La notice doit être traduite dans la langue du pays visé.")

    @pytest.fixture
    def req_risque(self):
        return Requirement("REQ-11", "Si le risque est élevé, un organisme notifié est requis.")

    # --- Tests REQ-06 (Langues) ---

    def test_req06_langue_conforme(self, req_langue):
        """Succès si le marché est la France et que le français est mentionné."""
        text = "Marches vises : France\nNotice : Disponible en Francais"
        product = parse_product_sheet(text)
        decision = evaluate_requirement(req_langue, product)
        assert decision.status == Status.SATISFAIT

    def test_req06_langue_manquante(self, req_langue):
        """Échec si le marché est l'Italie mais la notice est uniquement en Français."""
        text = "Marches : Italie\nNotice : Uniquement en Francais mais italien non"
        product = parse_product_sheet(text)
        decision = evaluate_requirement(req_langue, product)
        assert decision.status == Status.NON_SATISFAIT
        assert "Notice manquante" in decision.reason

    # --- Tests REQ-11 (Risques) ---

    def test_req11_risque_faible_sans_organisme(self, req_risque):
        """Risque faible = SATISFAIT même sans organisme."""
        text = "Niveau de risque : Faible\nOrganisme : Aucun"
        product = parse_product_sheet(text)
        decision = evaluate_requirement(req_risque, product)
        assert decision.status == Status.SATISFAIT
        assert "non requise" in decision.reason

    def test_req11_risque_eleve_avec_organisme(self, req_risque):
        """Risque élevé + Organisme présent = SATISFAIT."""
        text = "Risque : Critique\AXA : Organisme Notifie"
        product = parse_product_sheet(text)
        decision = evaluate_requirement(req_risque, product)
        assert decision.status == Status.SATISFAIT

    def test_req11_risque_eleve_sans_organisme(self, req_risque):
        """Risque élevé + Organisme absent = NON SATISFAIT."""
        text = "Risque : Eleve\nOrganisme : Absent"
        product = parse_product_sheet(text)
        decision = evaluate_requirement(req_risque, product)
        assert decision.status == Status.NON_SATISFAIT


class TestGeneralDecision:

    def test_decision_ambigue(self):
        """Vérifie que l'absence de marqueurs clairs mène à AMBIGU."""
        req = Requirement("REQ-99", "Le test de pression doit être validé.")
        # On mentionne la pression mais sans dire si c'est OK ou NON
        text = "Pression : Mesure en cours"
        product = parse_product_sheet(text)
        decision = evaluate_requirement(req, product)
        assert decision.status == Status.AMBIGU
        assert decision.missing_info is not None

    def test_decision_non_satisfait_explicite(self):
        """Vérifie la détection d'une non-conformité claire."""
        req = Requirement("REQ-05", "Signature du directeur requise.")
        text = "Signature : Non"
        product = parse_product_sheet(text)
        decision = evaluate_requirement(req, product)
        assert decision.status == Status.NON_SATISFAIT

    def test_absence_de_preuve(self):
        """Si aucun mot-clé ne matche, la décision est NON SATISFAIT."""
        req = Requirement("REQ-01", "Certificat de peinture.")
        text = "Voltage : 230V\nDimensions : 10x10"
        product = parse_product_sheet(text)
        decision = evaluate_requirement(req, product)
        assert decision.status == Status.NON_SATISFAIT
        assert "Aucune preuve" in decision.reason