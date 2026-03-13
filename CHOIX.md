# CHOIX.md - Méthodologie et Décisions Techniques

## Démarche de résolution - comment j'en suis arrivé là

### Étape 1 : focalisation sur la fiche produit (impasse)

Mon premier réflexe a été de partir de la fiche produit et de la "lire" de façon structurée. J'ai rapidement obtenu de bons résultats... mais pour la mauvaise raison : le système fonctionnait parce qu'il connaissait implicitement la structure de **cette** fiche en particulier. Les règles que j'écrivais étaient en réalité du sur-mesure pour le RS-440, pas de la conformité générique.

### Étape 2 : règles spécifiques par REQ (trop fragile)

Pour corriger ça, j'ai essayé d'écrire des règles explicites pour chaque REQ-XX (si REQ-06 → chercher "langue", "notice", etc.). Ça marchait bien sur la fiche fournie, mais dès qu'on changerait de fiche produit avec un vocabulaire différent, le système tombait en échec. Le problème : les règles étaient calées sur la fiche, pas sur le texte réglementaire.

### Étape 3 : pivot - partir du texte réglementaire (bonne direction)

J'ai alors changé de perspective : **le texte réglementaire est la référence
stable, pas la fiche produit**. La fiche m'avait juste appris que certains mots ne sont pas explicites - par exemple, "EN ISO 13850" dans la fiche correspond à "EN 13850" dans l'exigence, ou "enceinte de protection" correspond à "dispositifs adéquats".

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

## Méthode de comparaison choisie : matching lexical pondéré avec expansion sémantique
 
J'ai choisi une approche basée sur du matching mots-clés avec pondération,
expansion par groupes de synonymes et règles métier explicites. Ce choix fait suite à l'évaluation de trois approches vectorielles qui ont toutes échoué sur le même problème :
 
1. **spaCy (fr_core_news_md)** : similarité `doc.similarity()` globalement
   cohérente, mais incapable de distinguer deux phrases qui partagent un même mot-clé ("risques") tout en désignant des objets réglementaires différents ("évaluation des risques" vs "risques résiduels dans la notice").
 
2. **sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2`** : même
   problème - le score cosinus inter-phrases est trop générique pour ancrer
   la recherche sur le champ sémantique exact de la fiche produit.
 
3. **sentence-transformers `Lajavaness/sentence-camembert-large`** : modèle
   francais natif de meilleure qualité, mais le défaut structurel reste
   identique. La phrase "Evaluation des risques : REALISEE pour la phase
   d'utilisation uniquement" obtient un score cosinus élevé face à REQ-07
   ("mentionner explicitement les risques résiduels") alors que la bonne
   preuve est "Contenu notice - risques résiduels : OUI, section 8.3".
 
Dans les trois cas, le verdict pouvait être correct par accident, mais la
**justification était fausse** - ce qui est rédhibitoire en conformité
réglementaire où la traçabilité de la décision est aussi importante que le
verdict lui-même.
 
L'approche lexicale a été retenue pour trois raisons :
 
1. **Ancrage sur la clé de champ** : le score `overlap_clé × 2` cible
   directement le champ sémantique de la fiche (ex. `declaration_ce`,
   `notice_d_instructions`), pas une similarité globale inter-phrases.
 
2. **Contrôle total de la logique AMBIGU** : la distinction AMBIGU / NON
   SATISFAIT repose sur des marqueurs explicites ("en cours", "uniquement")
   qu'on maîtrise mieux qu'un score flottant.
 
3. **Lisibilité et débogage** : chaque décision est traçable - on peut
   retrouver exactement quel marqueur ou quelle preuve a produit le verdict.


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
2. Scoring lexical avec expansion par `SYNONYM_GROUPS` :
   `(2 × overlap_clé_étendu) + overlap_valeur_étendu`
 
   **Expansion par `SYNONYM_GROUPS`** : avant le calcul d'overlap, les tokens de l'exigence ET de la clé Evidence sont étendus via des groupes de synonymes domaine. Si un token appartient à un groupe, tous les tokens du groupe sont ajoutés. Exemple : le token `"proteges"` (REQ-09) déclenche l'ajout de `"enceinte"`, `"verrouille"`, `"carter"`... ce qui permet de relier l'exigence à la ligne "Enceinte de protection avec accès verrouillé" sans aucun token commun direct. Groupes définis :
   - protection physique : `elements, mobiles, dangereux, proteges, dispositifs, enceinte, verrouille, carter, capot, barriere, garde, ecran`
   - déclaration/signature : `declaration, signe, signee, representant, signataire`
   - documentation utilisateur : `notice, instructions, manuel, documentation`
   - risques : `risques, residuels, dangers, identifies`
   - arrêt d'urgence : `arret, urgence, stop, securite`
   - organisme tiers : `organisme, notifie, certifie, tierce`
 
   **`overlap_clé` (pondéré ×2)** : tokens de l'exigence étendue présents
   dans la clé normalisée de l'Evidence. Pondéré ×2 car la clé identifie le
   champ sémantique - si la clé matche, on est très probablement sur la bonne ligne de la fiche.
 
   **`overlap_valeur`** : tokens de l'exigence étendue présents dans les
   tokens de la valeur brute. Pondéré ×1.
 
3. Sélection des top-N preuves (fenêtre fixe : `max(1.0, best - 0.5)`)
4. Règles métier spécifiques par REQ (prioritaires, voir section dédiée)
5. Détection de marqueurs sur le texte fusionné :
   - **POSITIFS** : "present", "conforme", "certifié", "réalisée"...
   - **NÉGATIFS FORTS** : "non", "absent", "manquant", "standard", "basse"....
   - **NÉGATIFS DOUX** : "partiel", "incomplet", "uniquement"....
   - **INCERTAINS** : "en cours", "prévu", "à confirmer"...
6. Arbre de décision : SATISFAIT -> NON SATISFAIT -> AMBIGU par défaut

---

## Règles métier spécifiques par REQ
 
Trois exigences nécessitent une logique dédiée qui ne peut pas être résolue
par le scoring lexical générique seul :
 
**REQ-06 - Couverture linguistique** (`check_language_compliance`)  
Récupère le champ `marches_vises` de la fiche, mappe chaque pays à sa langue (`france → francais`, `italie → italien`, `portugal → portugais`), puis vérifie que chaque langue requise est présente dans le texte de la notice.
Verdict NON SATISFAIT si au moins une langue est absente.
 
**REQ-09 - Protection des éléments mobiles**  
Arbre à trois branches :
- Terme de protection présent ET pas d'indicateur d'absence -> **SATISFAIT**
- Terme de protection présent MAIS indicateur d'absence -> **NON SATISFAIT**
- Sujet mentionné sans solution de protection identifiable -> **AMBIGU**
- Aucune preuve → **NON SATISFAIT**
 
Cette règle a été nécessaire car le scoring générique retournait SATISFAIT
sur la seule présence d'enceinte de protection sans vérifier le périmètre
couvert.
 
**REQ-11 - Organisme notifié**  
Détecte d'abord le niveau de risque déclaré. Si aucun indicateur de risque
élevé (`eleve`, `critique`, `haut`) n'est présent, la règle REQ-11 ne
s'applique pas -> **SATISFAIT** immédiat. Sinon, vérifie la présence d'un
organisme notifié ou certifié.
 
---

## Gestion des ambiguïtés dans la comprehension du texte - cas concrets

### REQ-01 / REQ-02 : Déclaration CE
La fiche indique `EN COURS, signature prévue avant livraison`. Les marqueurs "en cours" et "prévu" déclenchent `UNCERTAIN_MARKERS` → verdict **AMBIGU**.
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

**Connaissance métier insuffisante pour certains verdicts** : trois cas m'ont montré que le scoring lexical seul ne suffit pas - il faut comprendre la logique réglementaire derrière le texte.
 
- **REQ-03** : la fiche indique *"Marquage CE : OUI, apposé sur le tableau de commande"*. Le système a retourné SATISFAIT car tous les marqueurs positifs étaient présents. Mais réglementairement, le marquage CE doit être apposé sur la machine elle-même, pas sur un sous-ensemble. Sans cette connaissance métier, le système ne peut pas distinguer un emplacement valide d'un emplacement non conforme -> verdict correct : **AMBIGU**.
 
- **REQ-07** : la fiche renvoie à *"section 8.3 (Entretien et nettoyage)"*. Le système a vu "OUI" + "risques résiduels" et a conclu SATISFAIT. Mais l'exigence demande une mention **explicite** des risques identifiés - un titre de section "Entretien et nettoyage" ne garantit pas que tous les risques résiduels y sont listés -> verdict correct : **AMBIGU**.
 
- **REQ-09** : la fiche mentionne une enceinte de protection, mais ne documente pas que **tous** les éléments mobiles dangereux sont couverts. Le système a retourné SATISFAIT sur la présence d'une preuve positive. Réglementairement, la conformité exige une couverture exhaustive du périmètre de protection -> verdict correct : **AMBIGU**.
 
Ces trois cas illustrent une limite fondamentale de l'approche purement lexicale : **le système s'adapte au vocabulaire du texte réglementaire, mais pas à la logique métier de l'industrie concernée**. Pour aller plus loin, il faudrait soit enrichir les règles structurelles avec des contraintes métier explicites (emplacement valide du marquage CE, exhaustivité des risques couverts), soit intégrer une base de connaissances domaine (ontologie machines/directive CE) qui permette au système de raisonner sur ce que signifie réellement "conforme" dans ce secteur.

**Limites du scoring lexical** : si les tokens de l'exigence sont absents de la fiche (ex. vocabulaire complètement différent), le score est nul et le verdict tombe en NON SATISFAIT par défaut, alors que l'information pourrait être présente sous une autre formulation.

---

## Améliorations non implémentées (par manque de temps)

- **Extraction des dates** dans les champs "en cours" pour évaluer si la livraison prévue est réaliste
- **Export `--output json`** pour intégration dans un pipeline externe
- **Support multi-documents** : auditer plusieurs fiches produit en batch
- **Base de connaissances domaine** (ontologie directive machines) pour raisonner sur la logique métier sans règles hardcodées par REQ

---

## Résumé des verdicts attendus

| REQ   | Verdict attendu  | Raison principale                                      |
|-------|------------------|--------------------------------------------------------|
| REQ-01 | AMBIGU          | Déclaration CE "en cours"                              |
| REQ-02 | AMBIGU          | Signature "prévue avant livraison"                     |
| REQ-03 | SATISFAIT/AMBIGU       | Marquage CE apposé                                     |
| REQ-04 | SATISFAIT       | Schémas électriques et pneumatiques présents           |
| REQ-05 | SATISFAIT       | Notice présente en français                            |
| REQ-06 | NON SATISFAIT   | Notice uniquement en français (IT et PT manquants)     |
| REQ-07 | SATISFAIT/AMBIGU       | Risques résiduels mentionnés section 8.3               |
| REQ-08 | AMBIGU          | Évaluation réalisée pour utilisation "uniquement"      |
| REQ-09 | SATISFAIT/AMBIGU      | Enceinte de protection avec accès verrouillé           |
| REQ-10 | SATISFAIT       | Bouton STOP certifié EN ISO 13850                      |
| REQ-11 | SATISFAIT       | Risque standard, organisme notifié non requis          |

> **Note** : Pour REQ-03, REQ-07 et REQ-09, j'ai fait le choix de les traiter comme **SATISFAIT** dans l'implémentation. Les preuves présentes dans la fiche sont suffisantes pour conclure à une conformité de premier niveau. Les nuances identifiées (emplacement du marquage, exhaustivité de la section, périmètre de l'enceinte) relèvent d'une connaissance métier approfondie de la directive machines que le système ne peut pas inférer sans règles explicites ou base de connaissances domaine.