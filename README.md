# Audit de conformité réglementaire 

Pipeline Python d'audit de conformité réglementaire : Lit un texte réglementaire et une fiche produit, compare les deux, et produit un rapport classant chaque exigence en **SATISFAIT**, **NON SATISFAIT** ou **AMBIGU**.

## Prérequis

- Python 3.10+

## Installation

```bash
pip install -r requirements.txt
```

## Lancer l'audit

```bash
python audit.py --req data/texte_reglementaire.txt --prod data/fiche_produit.txt
```
