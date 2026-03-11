# CHOIX.md - Méthodologie et Décisions techniques

## Démarche de résolution - comment j'en suis arrivé là

### Étape 1 : focalisation sur la fiche produit (impasse)

Mon premier réflexe a été de partir de la fiche produit et de la "lire" de façon structurée. J'ai rapidement obtenu de bons résultats... mais pour la mauvaise raison : le système fonctionnait parce qu'il connaissait implicitement la structure de **cette** fiche en particulier. Les règles que j'écrivais étaient en réalité du sur-mesure pour le RS-440, pas de la conformité générique.

### Étape 2 : règles spécifiques par REQ (trop fragile)

Pour corriger ça, j'ai essayé d'écrire des règles explicites pour chaque REQ-XX (si REQ-06 → chercher "langue", "notice", etc.). Ça marchait bien sur la fiche fournie, mais dès qu'on changerait de fiche produit avec un vocabulaire différent, le système tombait en échec. Le problème : les règles étaient calées sur la fiche, pas sur le texte réglementaire.

### Étape 3 : pivot - partir du texte réglementaire (bonne direction)

J'ai alors changé de perspective : **le texte réglementaire est la référence
stable, pas la fiche produit**. La fiche m'avait juste appris que certains mots ne sont pas explicites — par exemple, "EN ISO 13850" dans la fiche correspond à "EN 13850" dans l'exigence, ou "enceinte de protection" correspond à "dispositifs adéquats".

Cette observation m'a conduit à définir un **vocabulaire ancré sur le texte
réglementaire** : extraire les tokens significatifs de chaque REQ, puis les
chercher dans la fiche - quelle que soit sa structure. La fiche devient un
espace de recherche, pas un format attendu.

### Ce que la fiche m'a appris de concret

En analysant les divergences entre les deux textes, j'ai constitué les listes
de marqueurs (POSITIFS, NÉGATIFS, INCERTAINS) en observant les formulations
réelles utilisées dans les fiches produit industrielles. Ce n'est pas un
dictionnaire générique : c'est un vocabulaire calibré sur ce type de document
réglementaire (directive machines, marquage CE).

---

## Méthode de comparaison choisie : matching lexical pondéré

J'ai choisi une approche **sans librairie NLP externe**, basée sur du matching mots-clés avec pondération et détection de marqueurs linguistiques. Ce choix est motivé par trois raisons :

1. **Adéquation au problème** : les textes réglementaires et les fiches produit partagent un vocabulaire technique stable et prévisible. Une similarité cosinus sur des embeddings apporterait peu de valeur supplémentaire sur un corpus aussi petit (11 exigences, ~30 champs).

2. **Contrôle total de la logique AMBIGU** : l'enjeu central de l'exercice est de distinguer AMBIGU de NON SATISFAIT. Cette distinction repose sur des
nuances sémantiques précises ("en cours", "partiel", "uniquement") que l'on maîtrise mieux avec des marqueurs explicites qu'avec un score flottant.

3. **Lisibilité et débogage** : chaque décision est traçable - on peut retrouver exactement quel marqueur ou quelle preuve a produit le verdict.

---

## Architecture du pipeline

Le pipeline est découpé en trois étapes strictement séparées :

**Étape 1 - Parsing réglementaire** (`parse_requirements`)  
Extraction des REQ via regex lookahead entre deux identifiants consécutifs.
Un fallback ligne-par-ligne gère les textes sans identifiants REQ explicites.

**Étape 2 - Parsing fiche produit** (`parse_product_sheet`)  
Chaque ligne `Clé : Valeur` produit un objet `Evidence` avec :
- une clé normalisée en snake_case (suppression des accents, caractères spéciaux)
- un ensemble de tokens pour le scoring lexical

Les clés dupliquées sont concaténées avec ` | ` pour ne rien perdre.

**Étape 3 - Évaluation et rapport** (`evaluate_requirement`)  
Pour chaque exigence :
1. Extraction des mots-clés significatifs (hors stopwords, longueur > 2)
2. Scoring lexical de chaque Evidence : `(2 × overlap_clé) + overlap_valeur + 0.5 × partial_bonus`

   **`overlap_clé` (pondéré ×2)** : nombre de tokens de l'exigence présents
   dans la clé normalisée de l'Evidence (ex. `declaration_ce`). La clé est
   pondérée ×2 car elle identifie le champ sémantique - si la clé matche,
   on est très probablement sur la bonne ligne de la fiche.

   **`overlap_valeur`** : nombre de tokens de l'exigence présents dans la
   valeur brute de l'Evidence (ex. `EN COURS, signature prevue`). Pondéré ×1
   car la valeur contient souvent des mots parasites qui peuvent fausser le
   score.

   **`partial_bonus` (pondéré ×0.5)** : bonus accordé quand un token de
   l'exigence est contenu dans un token de la fiche, ou inversement - sans
   être identique. Par exemple, `"proteges"` est contenu dans `"protection"`,
   `"dispositif"` est contenu dans `"dispositifs"`. Ce bonus permet de relier
   des formes morphologiquement proches (singulier/pluriel, radical commun)
   sans avoir recours à un dictionnaire de synonymes. Il est délibérément
   faible (×0.5) pour ne pas faire remonter des faux positifs.

   **Injection de la section courante** : au moment du parsing, les tokens
   du titre de section (`securite`, `documentation`, `marquage`...) sont
   ajoutés aux tokens de chaque Evidence qui suit. Ainsi, une ligne sous
   `--- SECURITE ---` porte le token `"securite"` dans son ensemble de tokens,
   ce qui renforce son score face à une exigence qui parle de protection ou
   de dispositifs de sécurité.
3. Sélection des top-N preuves les plus pertinentes
4. Détection de marqueurs sur le texte fusionné :
   - **POSITIFS** : "present", "conforme", "certifié", "réalisée"...
   - **NÉGATIFS FORTS** : "non", "absent", "manquant", "standard"...
   - **NÉGATIFS DOUX** : "partiel", "incomplet", "uniquement"...
   - **INCERTAINS** : "en cours", "prévu", "à confirmer"...
5. Arbre de décision : SATISFAIT → NON SATISFAIT → AMBIGU par défaut

---

## Gestion des ambiguïtés - cas concrets

### REQ-01 / REQ-02 : Déclaration CE
La fiche indique `EN COURS, signature prévue avant livraison`. Les marqueurs
"en cours" et "prévu" déclenchent `UNCERTAIN_MARKERS` → verdict **AMBIGU**.
Ce n'est pas NON SATISFAIT car l'information est présente et la démarche
engagée, mais on ne peut pas conclure à la conformité sans la signature.

### REQ-06 : Notice dans la langue de chaque pays
La fiche mentionne France, Italie, Portugal comme marchés visés, mais la notice n'est disponible qu'en français. La fonction `check_language_compliance` détecte dynamiquement les pays et vérifie la présence des langues correspondantes → verdict **NON SATISFAIT** (manque italien et portugais).

### REQ-08 : Évaluation des risques
La fiche indique `REALISEE pour la phase d'utilisation uniquement`. Le marqueur "uniquement" (SOFT_NEGATIVE) coexiste avec "réalisée" (POSITIF) → verdict **AMBIGU** : l'évaluation existe mais ne couvre pas le cycle de vie complet.

### REQ-10 : Arrêt d'urgence EN 13850
La fiche cite `EN ISO 13850`, qui est la version harmonisée ISO de EN 13850.
Le token "13850" est présent dans les deux textes → verdict **SATISFAIT**.

### REQ-11 : Organisme notifié
La fiche indique `Catégorie de risque : standard (pas de catégorie spéciale)`. Le marqueur "standard" est dans `HARD_NEGATIVE_MARKERS` et le niveau de risque détecté ne requiert pas d'organisme notifié → verdict **SATISFAIT** (la règle ne s'applique pas à ce produit).

---

## Ce qui m'a bloqué

**Vocabulaire divergent entre exigences et fiche produit** : c'est le problème central. Exemples rencontrés :
- "circuits de commande" (REQ-04) vs "schémas électriques et pneumatiques"
- "dispositifs de protection" (REQ-09) vs "enceinte de protection avec accès verrouillé"
- "EN 13850" (REQ-10) vs "EN ISO 13850"

La normalisation en snake_case et le tokenizing sur les deux champs (clé + valeur) permettent de rapprocher ces formulations, mais un matching sémantique (embeddings) serait plus robuste pour des cas très divergents.

**Limites du scoring lexical** : si les tokens de l'exigence sont absents de la fiche (ex. vocabulaire complètement différent), le score est nul et le verdict tombe en NON SATISFAIT par défaut, alors que l'information pourrait être présente sous une autre formulation.

---

## Améliorations non implémentées (par manque de temps)

- **Embeddings sémantiques** (sentence-transformers) pour gérer les paraphrases et synonymes sans liste explicite de marqueurs
- **Extraction des dates** dans les champs "en cours" pour évaluer si la livraison prévue est réaliste
- **Scoring de confiance** numérique en complément du verdict ternaire, pour ordonner les AMBIGU par niveau de risque

---

## Résumé des verdicts attendus

| REQ   | Verdict attendu  | Raison principale                                      |
|-------|------------------|--------------------------------------------------------|
| REQ-01 | AMBIGU          | Déclaration CE "en cours"                              |
| REQ-02 | AMBIGU          | Signature "prévue avant livraison"                     |
| REQ-03 | SATISFAIT       | Marquage CE apposé                                     |
| REQ-04 | SATISFAIT       | Schémas électriques et pneumatiques présents           |
| REQ-05 | SATISFAIT       | Notice présente en français                            |
| REQ-06 | NON SATISFAIT   | Notice uniquement en français (IT et PT manquants)     |
| REQ-07 | SATISFAIT       | Risques résiduels mentionnés section 8.3               |
| REQ-08 | AMBIGU          | Évaluation réalisée pour utilisation "uniquement"      |
| REQ-09 | SATISFAIT       | Enceinte de protection avec accès verrouillé           |
| REQ-10 | SATISFAIT       | Bouton STOP certifié EN ISO 13850                      |
| REQ-11 | SATISFAIT       | Risque standard, organisme notifié non requis          |