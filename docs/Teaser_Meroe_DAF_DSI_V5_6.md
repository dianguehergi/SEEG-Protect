# MEROE V5.6 - Teaser DAF + DSI

> Mise a jour projet : les complements fraude MEROE V6.4 sont disponibles dans
> `docs/Flux_Fraude_MEROE_V6_4.md`, `docs/api_meroe_seeg_v1.yaml` et
> `docs/grille_fraude_seeg.csv`.

## 4 produits propres. 0 flou. B2B/B2C verrouille.

MEROE V5.6 est un pack de quatre produits concu pour aider la SEEG a recuperer
du revenu, reduire les impayes, proteger les clients prepayes et industrialiser
la detection de risque sur le parc EDAN.

Le principe est simple : MEROE ne vend pas une promesse abstraite. MEROE vend
un moteur de scoring, des offres transactionnelles ciblees et un service recurrent
d'alerte preventive. Chaque produit a un role clair, un modele economique clair
et un risque SEEG maitrise.

## Synthese executive

| Produit | Marche | Modele | Risque SEEG | CA MEROE annuel |
| --- | --- | --- | --- | --- |
| Scoring MEROE | B2B | 5% success fee | 0 FCFA si 0 recouvre | 2.5 Md FCFA |
| SOS Energie | B2C | Commission | 0 FCFA | Variable |
| SOS Gaz | B2C | Commission | 0 FCFA | Variable |
| PROTEC | B2B | Abonnement fixe | Fixe, budgetisable | 0.9 Md FCFA |
| Total B2B | B2B | Success fee + abonnement | ROI mesurable | 3.4 Md FCFA/an |

Valorisation indicative : 3.4 Md FCFA x 10 = 34 Md FCFA.

## Produit 1 - Scoring MEROE

**Role :** le moteur, le scanner, la preuve ROI.

Scoring MEROE scanne le parc EDAN 24/7 et produit deux listes exploitables par
la SEEG : une liste rouge fraude et une liste orange risque. Le produit est concu
pour parler a la Direction Financiere : pas de recouvrement, pas de facturation.

### 6 axes de scoring

1. **Axe technique EDAN :** bypass, tamper, inversion.
2. **Axe consommation :** chute de 40%, profil vs voisinage, 0 kWh.
3. **Axe paiement :** retard J+12, frequence SOS, impaye superieur a 50k.
4. **Axe geographique :** zone de perte superieure a 25%, transformateur surcharge.
5. **Axe historique :** anciennete superieure a 10 ans, ancien fraudeur.
6. **Axe temps reel :** coupure automatique, tension anormale.

### Sortie operationnelle

J+2 apres ingestion des donnees :

- Liste rouge fraude.
- Liste orange risque.
- Priorisation terrain.
- Tracabilite des raisons de scoring.

### Modele economique

MEROE facture 5% uniquement si la SEEG recouvre grace aux listes produites.

```text
0 FCFA recouvre = 0 FCFA facture
```

### Complement V6.4 - Boucle fraude fermee

Le scoring fraude V6.4 formalise la boucle complete :

```text
Scanner MEROE -> Liste Rouge -> Terrain SEEG -> Statut EDAN -> Bordereau DAF -> Facture 5%
```

Points verrouilles :

- MEROE lit les signaux EDAN deja presents : tension, tamper, 0 kWh, perte
  transformateur, inversion flux.
- MEROE transmet un `id_compteur`, un score, un code fraude et un montant estime.
- La SEEG garde le terrain, le PV, le client et la caisse.
- La facturation MEROE se calcule sur le montant encaisse ou valide par bordereau
  DAF, avec prorata en cas de paiement partiel.
- Les flux standards restent anonymises : pas de nom client, pas de telephone,
  pas de PV huissier.

La grille fraude V6.4 ajoute les codes `BYPASS_SHUNT`, `BYPASS_AIMANT`,
`INV_PHASE`, `CAPOT_OUVERT`, `FRAUDE_SW` et `RACC_ILLICITE`.

## Produit 2 - SOS Energie

**Role :** cash immediat et reduction des impayes.

SOS Energie cible uniquement les clients en score orange 20-50. L'objectif est
de convertir un risque de coupure ou d'impaye en transaction immediate.

```text
Le client paie 2 000 FCFA
Le client recoit 2 400 kWh J+3 via API EDAN
Fenetre : H24
Modele : commission
```

Ce produit est B2C, mais il reste controle par le scoring B2B : il ne doit pas
etre ouvert a tout le monde, seulement aux profils a risque recuperable.

## Produit 3 - SOS Gaz

**Role :** cash immediat et fidelisation client.

SOS Gaz reprend la meme logique que SOS Energie, mais sur une fenetre mensuelle
plus stricte.

```text
Le client paie 4 950 FCFA
Le client recoit 5 500 FCFA gaz J+3
Fenetre : du 25 au 5 de chaque mois
Modele : commission
```

Le produit augmente la valeur client sans porter le risque en continu.

## Produit 4 - PROTEC

**Role :** revenu recurrent, anti-churn, alerte preventive.

PROTEC est le service d'alerte preventive pour les compteurs prepayes. Il vise
100% du parc EDAN, avec un paiement par la SEEG.

```text
Alerte USSD/SMS J-3 avant coupure
0 action client
250 FCFA x 300 000 compteurs x 12 mois
= 0.9 Md FCFA/an fixe
```

PROTEC stabilise le pack MEROE avec un revenu recurrent et une valeur metier
facile a expliquer : moins de coupures surprises, moins de friction client,
meilleure prevention.

## Lecture DAF

Pour la Direction Financiere, MEROE est lisible en trois lignes :

1. **Scoring MEROE** cree du recouvrement mesurable.
2. **PROTEC** cree du revenu recurrent budgetisable.
3. **SOS Energie et SOS Gaz** generent des commissions transactionnelles sans
   prise de risque directe.

Le coeur B2B est estime a 3.4 Md FCFA/an :

```text
2.5 Md FCFA/an Scoring
+ 0.9 Md FCFA/an PROTEC
= 3.4 Md FCFA/an B2B
```

## Lecture DSI

Pour la DSI, MEROE s'integre comme une couche analytique et transactionnelle
autour de l'existant EDAN.

Architecture cible :

```text
EDAN / SEEG
  -> donnees compteurs, paiements, consommation, incidents
MEROE Scoring
  -> calcul du risque sur 6 axes
MEROE Actions
  -> listes fraude/risque, offres SOS, alertes PROTEC
SEEG / Terrain / Client
  -> recouvrement, prevention, notification
```

L'integration doit rester progressive : demarrage par fichiers ou API, puis
industrialisation webhook/API une fois la preuve metier validee.

## Message de closing

MEROE V5.6 n'est pas un produit unique. C'est un pack coherent :

- un moteur B2B qui prouve le ROI ;
- deux offres B2C qui convertissent le risque en cash ;
- un service recurrent qui protege le client et stabilise le revenu.

Statut : 4 produits MEROE V5.6 final locked.
