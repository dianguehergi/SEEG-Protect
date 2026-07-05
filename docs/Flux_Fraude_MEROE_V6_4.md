# Flux fraude MEROE V6.4

## Objectif

Transformer le scanner MEROE en boucle operationnelle lisible par le CODIR, la
DSI, la DAF et l'equipe terrain :

```text
Data EDAN -> Scanner MEROE -> Liste Rouge -> Terrain SEEG -> Recouvrement -> Facture MEROE
```

MEROE ne vend pas un logiciel abstrait. MEROE vend du cash recouvre, avec une
commission uniquement sur les montants effectivement encaisses ou presumes
recouvres selon les statuts EDAN contractualises.

## Schema en 5 blocs

| Bloc | Input | Process | Output |
| --- | --- | --- | --- |
| 1. Scanner MEROE | Telereleve EDAN | IA detecte anomalie, tamper, conso 0, tension, voisinage | Score fraude, ex. 0.98 |
| 2. Statut SEEG | ID compteur | Planification, constat, coupure, suivi EDAN | Statut `PV_EMIS`, `COUPE`, `REACTIVE` |
| 3. Qualification | Agent terrain + huissier | Photos, PV, preuve terrain | Note 10, fraude caracterisee |
| 4. Montant | Code fraude SEEG | Grille PV + consommation non facturee estimee | Base facturable |
| 5. Total MEROE | Base recouvree | Success fee 5% HT, TVA selon contexte | Facture MEROE |

Flux cle :

- `MEROE -> SEEG` : `id_compteur`, `score_fraude`, `motif_fraude`, montant estime.
- `SEEG -> MEROE` : `statut_compteur`, `date_changement_statut`, `motif_reactivation`, montant encaisse ou reference bordereau.
- Pas de nom client, pas de PV huissier en flux standard, pas d'API en ecriture.

## Storytelling CODIR

1. L'IA lit les logs EDAN 24/7 et leve une alerte quand un compteur ment.
2. La SEEG garde le terrain : agents, huissier, coupure, PV.
3. La DAF encaisse les montants recouvres.
4. MEROE facture 5% HT du montant recouvre, au prorata si paiement partiel.

Resume :

```text
IA -> Agent -> Paiement -> Commission
```

## Donnees EDAN deja disponibles

| Signal | Source SEEG | Lecture MEROE |
| --- | --- | --- |
| Tension | Logs compteur EDAN | Compteur alimente mais consommation incoherente |
| Tamper log | Logs evenement EDAN | Ouverture capot ou manipulation |
| 0 kWh / 30j | Base facturation EDAN | Maison supposee vide, mais tension presente |
| Perte transformateur | Systeme reseau | Zone a pertes anormales |
| Inversion flux | Logs compteur EDAN | Entree/sortie ou flux negatif |

Position DSI :

```text
La SEEG a deja la donnee. MEROE apporte le scanner.
```

## Tamper, bypass et preuve

Un log EDAN est le compte-rendu horodate du compteur. Exemple :

```text
12/09/2026 14:32:11 | COMPTEUR: 123456789 | EVENT: COUVERCLE_OUVERT
12/09/2026 14:32:11 | COMPTEUR: 123456789 | TENSION: 220V | CONSO: 0W
12/09/2026 14:32:11 | COMPTEUR: 123456789 | EVENT: FLUX_NEGATIF
```

Regle metier :

```text
TAMPER + 0 kWh + tension presente = bypass probable = Liste Rouge = constat terrain
```

Cas type :

| Donnee EDAN | Lecture MEROE | Score |
| --- | --- | --- |
| `COUVERCLE_OUVERT` x7 | Manipulation repetee | Fraude |
| `0 kWh` sur 30 jours | Consommation impossible | Fraude |
| `220V` H24 | Alimente mais ne compte pas | Confirme |
| Perte trafo -22% | Cohorte reseau coherente | Confirme |

Verdict attendu : `score_fraude = 0.98`, `motif_fraude = BYPASS_AIMANT` ou
`BYPASS_SHUNT`.

## Facturation et controle DAF

Principe :

```text
Pas d'encaisse SEEG = pas de facture MEROE
MEROE = 5% HT du montant reellement encaisse, au prorata des paiements
```

| Cas | Montant PV | SEEG encaisse | MEROE facture |
| --- | ---: | ---: | ---: |
| Paiement total | 1 500 000 FCFA | 1 500 000 FCFA | 75 000 FCFA |
| Paiement partiel | 1 500 000 FCFA | 750 000 FCFA | 37 500 FCFA |
| Aucun paiement | 1 500 000 FCFA | 0 FCFA | 0 FCFA |

Verrous :

- API EDAN lecture seule : statut `COUPE` ou `REACTIVE`.
- Motif de reactivation attendu : `PAIEMENT_PV`.
- Bordereau DAF mensuel signe.
- Droit d'audit trimestriel sur 5% des dossiers Liste Rouge.
- Alerte audit si `REACTIVE` avec motif different de `PAIEMENT_PV`.

## Donnees agregees et anonymisees

MEROE ne doit pas recevoir de donnees personnelles en flux standard :

- pas de nom client ;
- pas de telephone client ;
- pas d'historique nominatif d'achat kWh ;
- pas d'acces a la base EDAN Vending ;
- pas d'API en ecriture.

La SEEG garde le lien `id_compteur -> client -> adresse`. MEROE travaille sur
les signaux techniques, les scores, les statuts et les montants agregeables pour
la DAF.

## Grille fraude SEEG

La grille est externalisee dans :

```text
docs/grille_fraude_seeg.csv
```

Regle :

```text
Base facturable = bareme PV + consommation non facturee estimee
```

En cas de cumul de fraudes, prendre le bareme le plus haut et ajouter une seule
consommation non facturee estimee, sauf arbitrage contractuel contraire.

## Fraude logicielle `FRAUDE_SW`

La fraude logicielle est invisible au terrain simple. MEROE sert a declencher le
dossier special, puis le laboratoire SEEG prouve.

| Procede | Signature data | Constat |
| --- | --- | --- |
| Firmware patche | Conso remontee tres inferieure a la conso physique theorique | Labo compare le hash firmware |
| Horloge RTC bloquee | Index bloque alors que tension et courant existent | Depose compteur sous scelle |
| Seuil modifie | Puissance anormale sans coupure ni evenement | Controle metrologie |

Process recommande :

1. MEROE detecte `FRAUDE_SW`, score superieur a 0.95.
2. SEEG classe le dossier en constat special, sans coupure automatique.
3. Deux agents, labo metrologie et huissier deposent le compteur sous scelle.
4. Le labo compare firmware/hash avec le referentiel SEEG.
5. Si l'ecart est confirme, PV `FRAUDE_SW` + NFE.

## Bordereau mensuel DAF

Endpoint cible :

```text
GET /v1/bordereau-mensuel?mois=2026-09&signature_daf=true
```

Contenu attendu :

```text
BORDEREAU DE RECOUVREMENT LISTE ROUGE MEROE
Periode : 01/09/2026 au 30/09/2026 - Article 8.4 V6.4

1. Nb dossiers Liste Rouge transmis MEROE
2. Nb dossiers statut EDAN = REACTIVE
3. Montant total PV estime
4. Montant total encaisse declare SEEG
5. Success fee MEROE 5% HT due
```

Le bordereau sert a fermer la boucle DAF : agreger, signer, facturer.

