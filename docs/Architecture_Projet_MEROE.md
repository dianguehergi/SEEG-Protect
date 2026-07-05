# Architecture globale SEEG Protect / MEROE

## Objectif final

Construire une plateforme pilote capable de demontrer, avec de fausses donnees
puis avec les vraies donnees EDAN, comment la SEEG peut :

- proteger les clients prepayes avec des alertes SMS ;
- detecter la fraude compteur ;
- suivre les statuts terrain ;
- calculer le cash recouvre ;
- piloter les indicateurs DAF/DSI dans un dashboard partenaire.

## Schema global

```text
                         +-------------------------+
                         |      Partenaires        |
                         |  DAF / DSI / Direction  |
                         +-----------+-------------+
                                     |
                                     v
+----------------+        +----------+-----------+        +----------------+
| Client prepaid |        | Dashboard partenaire |        | Equipe terrain |
| Compteur EDAN  |        | KPIs + dossiers      |        | Agent/Huissier |
+-------+--------+        +----------+-----------+        +--------+-------+
        |                            ^                             |
        | SMS / alerte               | lecture                     | constat/PV
        v                            |                             v
+-------+--------+        +----------+-----------+        +--------+-------+
| Fournisseur SMS|<-------| API SEEG Protect     |<-------| Statut EDAN    |
| stub puis reel |        | Webhooks + SQLite    |        | COUPE/REACTIVE |
+----------------+        +----------+-----------+        +--------+-------+
                                     ^                             |
                                     | donnees                     |
                                     |                             v
                         +-----------+------------+       +--------+-------+
                         | Simulation locale      |       | SEEG / EDAN    |
                         | faux compteurs         |       | vraies donnees |
                         +-----------+------------+       +----------------+
                                     |
                                     v
                         +-----------+------------+
                         | MEROE Scoring Fraude   |
                         | Liste Rouge + 5% fee   |
                         +------------------------+
```

## Flux 1 - Protection client

```text
Souscription -> Paiement -> Activation -> Solde faible -> SMS -> Dashboard
```

Ce flux existe deja dans le MVP. Les webhooks disponibles sont :

- `POST /webhooks/subscriptions`
- `POST /webhooks/payments`
- `POST /webhooks/low-balance`

## Flux 2 - Fraude MEROE V6.4

```text
Logs EDAN -> Score fraude -> Liste Rouge -> Terrain SEEG -> Statut EDAN
-> Montant encaisse -> Success fee MEROE -> Dashboard DAF
```

Webhooks ajoutes pour simuler puis brancher le reel :

- `POST /webhooks/fraud-cases`
- `POST /webhooks/fraud-status`
- `GET /fraud-cases?limit=50`

## Simulation avant vraies donnees

Le script suivant cree des compteurs fictifs, des alertes SMS et des dossiers
fraude visibles dans le dashboard :

```powershell
python scripts\demo_fraud_data.py
```

Les cas simules couvrent :

- compteur fraude reactive avec paiement ;
- compteur coupe sans recouvrement ;
- compteur reactive avec motif technique, donc alerte audit ;
- paiement partiel avec commission prorata.

Quand la SEEG donnera les vraies donnees, on remplacera simplement cette source
de simulation par les vrais webhooks ou fichiers EDAN. La logique dashboard reste
la meme.

## Ce que le dashboard doit montrer

| Zone | Indicateur | Utilite |
| --- | --- | --- |
| Protection client | Souscriptions, paiements, SMS | Montrer le MVP client |
| Fraude | Dossiers Liste Rouge | Montrer le pipe de recouvrement |
| DAF | Montant encaisse, fee MEROE | Montrer le ROI |
| DSI | Evenements, statuts, audit | Montrer la tracabilite |
| Terrain | `COUPE`, `REACTIVE`, motif | Suivre l'action SEEG |

## Competences demontrees

Ce projet montre les competences suivantes :

- conception produit B2B/B2C ;
- architecture API et webhooks signes HMAC ;
- modelisation de donnees metier ;
- dashboard partenaire ;
- simulation de donnees avant integration reelle ;
- securite minimale : token admin, signature webhook, lecture seule ;
- logique de scoring fraude et gestion des statuts ;
- calcul financier : recouvrement, prorata, success fee ;
- documentation DAF/DSI/dev ;
- preparation d'un pilote cloud deployable sur Render ou Azure.

## Prochaine etape

1. Generer les fausses donnees avec `scripts\demo_fraud_data.py`.
2. Ouvrir `/process` pour voir le parcours complet du client jusqu'a MEROE.
3. Ouvrir `/dashboard` et verifier les KPIs fraude.
4. Montrer `/fraud-cases?limit=20` a la DSI pour le JSON.
5. Valider avec la SEEG les vrais champs EDAN.
6. Remplacer progressivement la simulation par les donnees reelles.
