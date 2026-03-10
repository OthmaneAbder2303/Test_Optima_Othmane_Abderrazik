"""
TESTS UNITAIRES — EXIGENCES RÉGLEMENTAIRES (parse_requirements)

Ce module valide la robustesse de l'extraction des données sources.
Il s'assure que :
1. Le formatage des IDs (REQ-XX) est strictement respecté.
2. Le nettoyage des balises (===, ---) et des sauts de ligne est correct.
3. La cohérence logique (unicité, séquençage) des exigences est préservée.

Usage :
    python -m pytest test/test_parse_requirements.py --req data/texte_reglementaire.txt
"""

from audit import parse_requirements
import os
import re
import pytest

# Récupération des chemins via options pytest

@pytest.fixture(scope="session")
def req_text(request):
    path = request.config.getoption("--req")
    if path:
        assert os.path.exists(path), f"Fichier introuvable : {path}"
        with open(path, encoding="utf-8") as f:
            return f.read()

@pytest.fixture(scope="session")
def requirements(req_text):
    return parse_requirements(req_text)


# Tests

class TestParseRequirements:

    # Structure générale

    def test_au_moins_une_exigence_extraite(self, requirements):
        """Le fichier doit contenir au moins une exigence REQ-XX."""
        assert len(requirements) > 0, "Aucune exigence extraite — vérifier le format du fichier."

    def test_ids_au_format_REQ_XX(self, requirements):
        r"""Chaque id doit correspondre exactement au pattern REQ-\d{2}."""
        pattern = re.compile(r"^REQ-\d{2}$")
        for r in requirements:
            assert pattern.match(r.id), f"ID malformé : '{r.id}'"

    def test_ids_uniques(self, requirements):
        """Deux exigences ne peuvent pas partager le même id."""
        ids = [r.id for r in requirements]
        assert len(ids) == len(set(ids)), f"IDs dupliqués : {[x for x in ids if ids.count(x) > 1]}"

    # ici j'ai suppose qu'on est exigeant sur la qualité de la source de données; pas de trou
    def test_ids_ordonnes_sequentiellement(self, requirements):
        """Les ids doivent se suivre sans trou (REQ-01, REQ-02, …)."""
        nums = sorted(int(r.id.split("-")[1]) for r in requirements)
        expected = list(range(1, len(nums) + 1))
        assert nums == expected, f"Séquence avec trou ou désordre : {nums}"


    # Contenu des textes

    def test_texte_non_vide(self, requirements):
        """Aucune exigence ne doit avoir un texte vide."""
        for r in requirements:
            assert r.text.strip(), f"{r.id} a un texte vide."

    def test_texte_sans_balises_section(self, requirements):
        """Les balises === … === ne doivent pas apparaître dans les textes."""
        for r in requirements:
            assert "===" not in r.text, f"{r.id} contient une balise de section."

    def test_texte_sans_id_residuel(self, requirements):
        """Le texte d'une exigence ne doit pas commencer par son propre id."""
        for r in requirements:
            assert not r.text.startswith(r.id), \
                f"{r.id} : l'id est répété en début de texte : '{r.text[:40]}'"

    def test_texte_minimum_20_caracteres(self, requirements):
        """Un texte trop court est probablement un artefact de parsing."""
        for r in requirements:
            assert len(r.text) >= 20, \
                f"{r.id} : texte trop court ({len(r.text)} car.) : '{r.text}'"

    def test_pas_de_retour_ligne_dans_texte(self, requirements):
        """Les multi-lignes doivent être joints en une seule chaîne."""
        for r in requirements:
            assert "\n" not in r.text, \
                f"{r.id} : retour à la ligne non supprimé dans le texte."


    # Robustesse

    def test_texte_vide_retourne_liste_vide(self):
        assert parse_requirements("") == []

    def test_texte_sans_req_retourne_liste_vide(self):
        assert parse_requirements("Aucune exigence ici.\n=== FIN ===") == []

    def test_req_unique(self):
        reqs = parse_requirements("REQ-01 : Texte unique sans suite.")
        assert len(reqs) == 1
        assert reqs[0].id == "REQ-01"
        assert "Texte unique" in reqs[0].text

    def test_req_multilignes_jointes(self):
        text = "REQ-01 : Première ligne\ncontinuée ici.\nREQ-02 : Autre."
        reqs = parse_requirements(text)
        assert "Première ligne" in reqs[0].text
        assert "continuée ici" in reqs[0].text

    def test_espaces_multiples_normalises(self):
        text = "REQ-01 :   Texte   avec    espaces   multiples."
        reqs = parse_requirements(text)
        assert "  " not in reqs[0].text, "Les espaces multiples doivent être normalisés."

    def test_header_footer_ignores(self):
        text = "=== HEADER ===\nREQ-01 : Valide.\n=== FIN ==="
        reqs = parse_requirements(text)
        assert len(reqs) == 1
        assert reqs[0].text == "Valide."