"""
TESTS UNITAIRES — PIPELINE D'INGESTION DE DONNÉES (Audit de Conformité)

Ce module valide la robustesse de l'extraction des deux sources du pipeline :
1. Les exigences réglementaires (parse_requirements) :
   - Respect strict du format d'ID (REQ-XX).
   - Nettoyage des balises structurelles (===, ---) et des sauts de ligne.
   - Cohérence logique (unicité, séquençage) et mécanisme de fallback.

2. La fiche produit (parse_product_sheet) :
   - Normalisation des clés en snake_case.
   - Fusion intelligente des clés dupliquées (concaténation).
   - Traitement des notes libres et génération des tokens de recherche.

Usage :
    python -m pytest test/test_parsing.py
"""

import pytest
from audit import parse_requirements, Requirement, parse_product_sheet, Evidence, ProductData

class TestParseRequirements:

    # 1. Tests de parsing standard
    def test_parsing_standard_avec_id(self):
        text = "REQ-01 : Marquage CE.\nREQ-02 : Notice incluse."
        reqs = parse_requirements(text)
        assert len(reqs) == 2
        assert reqs[0].req_id == "REQ-01"
        assert reqs[0].description == "Marquage CE."

    # 2. Tests de la stratégie de secours (Fallback)
    def test_fallback_numérotation_auto(self):
        """Si aucun REQ n'est trouvé, le script doit numéroter lui-même."""
        text = "Premier point obligatoire.\nDeuxième point de conformité."
        reqs = parse_requirements(text)
        assert len(reqs) == 2
        assert reqs[0].req_id == "REQ-01"
        assert "Premier point" in reqs[0].description

    def test_fallback_nettoyage_puces(self):
        """Vérifie que les puces ou listes sont bien nettoyées en fallback."""
        text = "- Premier point.\n1. Deuxième point."
        reqs = parse_requirements(text)
        assert "Premier point" in reqs[0].description
        assert "Deuxième point" in reqs[1].description

    # 3. Tests de robustesse (Nettoyage)
    def test_normalisation_des_ids(self):
        """Vérifie que REQ 01, REQ_01 et REQ-01 sont traités de la même façon."""
        text = "REQ 01 : Test1\nREQ_02 : Test2"
        reqs = parse_requirements(text)
        assert reqs[0].req_id == "REQ-01"
        assert reqs[1].req_id == "REQ-02"

    def test_header_footer_ignores(self):
        text = "=== HEADER ===\nREQ-01 : Valide.\n=== FIN ==="
        reqs = parse_requirements(text)
        assert len(reqs) == 1
        assert reqs[0].description == "Valide."

    # 4. Gestion des erreurs
    def test_erreur_si_aucun_contenu(self):
        text_invalide = "trop"
        with pytest.raises(ValueError, match="Aucune exigence exploitable n'a ete detectee dans le texte reglementaire."):
            parse_requirements(text_invalide)


class TestParseProductSheet:

    def test_parsing_structure_standard(self):
        """Vérifie que les clés sont normalisées en snake_case."""
        text = "Marquage CE : OUI\nNotice en Français : Présente"
        data = parse_product_sheet(text)
        
        assert "marquage_ce" in data.fields
        assert "notice_en_francais" in data.fields
        assert data.fields["marquage_ce"] == "OUI"
        assert len(data.evidences) == 2

    def test_concatenation_cles_dupliquees(self):
        """Vérifie la fusion correcte des doublons avec ' | '."""
        text = "Note : Premier point\nNote : Deuxième point"
        data = parse_product_sheet(text)
        assert data.fields["note"] == "Premier point | Deuxième point"
        assert len(data.evidences) == 2

    def test_gestion_lignes_libres(self):
        """Vérifie que les notes sans ':' sont indexées par ligne."""
        text = "Ceci est une note technique importante"
        data = parse_product_sheet(text)
        
        # La clé doit être générée automatiquement via l'index de ligne
        assert any(e.key.startswith("ligne_") for e in data.evidences)
        assert data.evidences[0].value == "Ceci est une note technique importante"

    def test_tokenisation_pour_scoring(self):
        """Vérifie que les tokens sont générés pour la future comparaison."""
        text = "Voltage : 230V"
        data = parse_product_sheet(text)
        
        tokens = data.evidences[0].tokens
        assert "voltage" in tokens
        assert "230v" in tokens

    def test_ignore_separateurs(self):
        """S'assure que les séparateurs ne créent pas d'Evidence."""
        text = "=== SECTION ===\nClé : Valeur\n--- FIN ---"
        data = parse_product_sheet(text)
        assert len(data.evidences) == 1
        assert "cle" in data.fields