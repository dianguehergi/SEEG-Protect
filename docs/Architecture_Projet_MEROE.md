# Architecture globale MEROE CORE V3.2

## Positionnement final

MEROE CORE V3.2 est une seule plateforme SEEG, avec deux produits visibles dans
un meme portail :

- **SCORING Fraude** : priorite DG, detecter les pertes, qualifier les dossiers,
  recouvrer, facturer MEROE uniquement sur le resultat prouve ;
- **PROTEC** : rail client, prevenir les coupures pour les abonnes, reduire les
  reclamations et creer une recette recurrente.

Le message DG doit rester simple :

```text
Vous avez 1 portail. Vous gerez vos clients ET vous traquez les pertes.
Nous prenons 0 risque : si nous ne vous rapportons rien, vous ne nous payez rien.
```

## Pourquoi V3.2

Le besoin SEEG a evolue. PROTEC seul est utile, mais le sujet le plus urgent est
la perte commerciale et la fraude compteur. La plateforme doit donc presenter
PROTEC comme un produit complementaire et mettre le scoring fraude au centre de
la valeur financiere.

Le point fort : les deux rails demarrent avec une seule alimentation SEEG J+1.
Pas besoin d'imposer deux projets, deux SI, deux equipes ou deux budgets.

## Schema global

```text
                          +-----------------------------+
                          |          DG SEEG            |
                          | Vue executive + ROI global  |
                          +--------------+--------------+
                                         ^
                                         |
+----------------------+      +----------+-----------+      +----------------------+
| Donnees SEEG J+1     |----->| MEROE CORE Platform |----->| Portail SEEG unique  |
| 300 000 compteurs    |      | 1 moteur / 2 rails  |      | 4 dashboards         |
+----------+-----------+      +----------+-----------+      +----------+-----------+
           |                             |                             |
           |                             |                             |
           v                             v                             v
+----------+-----------+      +----------+-----------+      +----------+-----------+
| Rail 1 PROTEC        |      | Rail 2 SCORING       |      | PV / Facturation     |
| Abonnes parametres   |      | 300 000 compteurs EDAN|     | J+5, J+15, J+20      |
| SMS J-3 / J-1        |      | Liste Rouge > 80     |      | 10% MEROE prouve     |
+----------+-----------+      +----------+-----------+      +----------+-----------+
           |                             |
           v                             v
+----------+-----------+      +----------+-----------+
| Clients proteges     |      | Brigade fraude SEEG  |
| moins de coupures    |      | qualification terrain |
+----------------------+      +----------------------+
```

## Bloc 0 - Alimentation unique SEEG J+1

La SEEG pousse un seul fichier quotidien ou quasi quotidien pour alimenter les
deux produits.

Perimetre cible :

- 300 000 compteurs EDAN, soit le parc SEEG a scorer ;
- abonnes PROTEC selon la base active transmise par la SEEG ;
- 5 000 abonnes PROTEC = hypothese de pilote, pas une limite produit ;
- extension progressive apres pilote DG.

Colonnes minimales :

| Colonne | Usage PROTEC | Usage SCORING |
| --- | --- | --- |
| `numero_compteur` | Identifier abonne | Identifier compteur |
| `index_n` | Mesurer derniere conso | Detecter incoherence |
| `index_n_1` | Calculer variation | Detecter baisse/chute |
| `conso` | Seuil alerte client | Signal anomalie |
| `etat_sts` | Statut client | Couvercle, erreur, coupure, bypass |
| `recharges` | Historique recharge | Profil paiement suspect |
| `canal_paiement` | Repartition guichet/mobile | Ecart et anomalie de paiement |

Colonnes recommandees pour mieux pitcher :

- `nom_client` ;
- `telephone` ;
- `quartier` ;
- `ville` ;
- `date_releve` ;
- `montant_recharge_30j` ;
- `conso_moyenne_90j` ;
- `statut_protec`.

## Bloc 1 - Moteur MEROE

Le moteur separe la meme donnee en deux rails.

| Rail | Perimetre | Objectif | Logique | Sortie |
| --- | --- | --- | --- | --- |
| PROTEC | Base abonnes active, 5 000 en hypothese pilote | Prevenir les coupures, rassurer client | Si conso ou recharge sous seuil, SMS J-3/J-1 | SMS + paiement 300 FCFA |
| SCORING | 300 000 compteurs EDAN, parc SEEG | Detecter anomalies, recouvrer | Si score fraude > 80, Liste Rouge | Dashboard fraude + PV qualification |

### Rail 1 - PROTEC

PROTEC ne doit pas etre vendu comme le coeur du deal DG. Il sert a montrer que
MEROE protege aussi l'image client de la SEEG.

Perimetre :

- nombre d'abonnes parametre par la SEEG ;
- 5 000 abonnes est une indication de pilote pour dimensionner la demo ;
- le produit peut monter progressivement si la SEEG decide d'elargir PROTEC.

Regles :

- client abonne uniquement ;
- deux alertes maximum par cycle ;
- SMS J-3 et J-1 ;
- STOP client obligatoire ;
- suivi des reclamations et du taux de coupure evitee.

Modele economique :

- prix client : 300 FCFA/mois ;
- repartition a figer : part SEEG, part MEROE, cout SMS, taxes ;
- dashboard Finance visible des le pilote.

### Rail 2 - SCORING Fraude

Le scoring fraude est le coeur V3.2.

Signaux V1 simples, explicables au DG :

- chute de consommation superieure a 40% ;
- consommation nulle avec historique de recharge ;
- index incoherent ou negatif ;
- etat STS anormal ;
- canal de paiement inhabituel ;
- repetition d'anomalies sur plusieurs cycles.

Score :

```text
0-49  : normal
50-79 : surveillance
80-100: Liste Rouge
```

MEROE ne coupe pas, ne sanctionne pas et ne remplace pas la SEEG. MEROE priorise.
La Brigade Fraude SEEG qualifie ensuite le dossier.

## Bloc 2 - Les 4 dashboards dans un seul portail

### Dashboard 1 - DG SEEG

Vue executive, une page.

KPIs PROTEC :

- taux abonnement ;
- baisse reclamations ;
- recettes 30% ;
- SMS envoyes ;
- clients proteges.

KPIs SCORING :

- anomalies detectees ;
- compteurs Liste Rouge ;
- montant potentiel ;
- montant recouvre ;
- facture MEROE 10%.

Action :

- telecharger le PV de repartition J+5.

### Dashboard 2 - Service Client SEEG

Vue PROTEC.

Fonctions :

- liste des abonnes par quartier ;
- statuts `OK`, `ALERTE_J_3`, `URGENCE_J_1`, `COUPE` ;
- appel client ;
- historique SMS ;
- STOP et reclamations.

### Dashboard 3 - Finance SEEG

Vue repartition.

Onglets :

- pot guichet vs pot Airtel ;
- repartition automatique 30/70/16/2 ;
- ecarts et anomalies de paiement ;
- export PV repartition.

La formule 30/70/16/2 doit etre clarifiee contractuellement avant signature
pour eviter toute ambiguite entre part SEEG, part MEROE, cout operateur et taxes.

### Dashboard 4 - Brigade Fraude SEEG

Vue scoring.

Fonctions :

- carte Nzeng et extension autres zones ;
- points rouges Liste Rouge ;
- filtres score 80-100 ;
- filtres type anomalie : couvercle ouvert, chute conso, index incoherent ;
- bouton `Marquer comme Qualifie Fraude` ;
- champ `Montant recouvre`.

La facture 10% MEROE se declenche uniquement quand la SEEG marque le dossier
comme `QUALIFIE_FRAUDE` avec un montant recouvre ou valide.

## Bloc 3 - Circuit ferme J+1 a J+20

| Date | Action | Responsable | Sortie |
| --- | --- | --- | --- |
| J+1 | Envoi data 300 000 compteurs EDAN | SEEG | Fichier source horodate |
| J+2 | Calcul PROTEC + SCORING | MEROE | Alertes + Liste Rouge draft |
| J+3 | Envoi SMS PROTEC | MEROE | Journal SMS/DLR |
| J+5 | Envoi PV repartition + Liste Rouge | MEROE | PV officiel |
| J+15 | Retour qualification fraude | SEEG | PV qualification |
| J+20 | Facturation 10% | MEROE | Facture sur recouvrement prouve |

## Regle de facturation fraude

Principe DG :

```text
MEROE facture 10% uniquement sur les dossiers qualifies fraude par la SEEG
et rattaches a un montant recouvre ou valide.
```

Exemples :

| Cas | Montant recouvre | Statut SEEG | Facture MEROE |
| --- | ---: | --- | ---: |
| Suspicion non traitee | 0 | A_TRAITER | 0 |
| Fausse alerte | 0 | NON_FRAUDE | 0 |
| Fraude qualifiee sans recouvrement | 0 | QUALIFIE_FRAUDE | 0 |
| Fraude qualifiee avec 1 000 000 FCFA | 1 000 000 | QUALIFIE_FRAUDE | 100 000 |

## Ce qui doit etre montre au DG

1. Une seule plateforme, pas deux projets.
2. Une seule donnee SEEG J+1, reutilisee deux fois.
3. Une priorite financiere claire : scoring fraude.
4. Un produit client visible : PROTEC.
5. Un risque SEEG limite : MEROE gagne quand la SEEG recouvre.
6. Une boucle fermee : detection, qualification, encaissement, facture.

## Livrables V3.2

| Fichier | Contenu |
| --- | --- |
| `docs/CDC_MEROE_CORE_V3_2.md` | CDC combine : PROTEC, SCORING, donnees, repartition, 10% |
| `docs/Architecture_Projet_MEROE.md` | schema global 1 plateforme / 2 rails |
| `docs/ANNEXE_TECH_MEROE_CORE_V3_2.md` | format fichier J+1, PV qualification, regles techniques |
| `docs/CDC_PROTEC_RELIEF_V2_5.md` | archive utile du rail PROTEC seul |

## Prochaine etape

1. Preparer le pitch DG sur 6 slides maximum.
2. Creer un dataset demo de 300 compteurs dont 30 anomalies.
3. Adapter le dashboard local pour afficher les 4 vues V3.2.
4. Generer un PV Liste Rouge J+5 et un PV Qualification J+15.
5. Finaliser la regle contractuelle 10% sur recouvrement prouve.
