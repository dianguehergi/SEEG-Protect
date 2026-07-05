# Mise en ligne partenaire - SEEG Protect / MEROE

## Objectif

Mettre en ligne une version pilote consultable par les partenaires afin de suivre
l'avancement du projet, tester le scenario de demonstration et visualiser les
indicateurs metier.

## Pages a partager

- `/dashboard` : vue metier avec KPIs, graphiques, souscriptions et SMS.
- `/architecture` : explication du fonctionnement derriere le dashboard.
- `/roadmap` : suivi projet, avancement, lots et prochaines decisions.
- `/meter?meter_id=...` : fiche detail d'un compteur.

## Nouveaux livrables MEROE fraude V6.4

Les informations V6.4 ajoutent une brique "scoring fraude / Liste Rouge" au
projet. Elles sont documentees dans :

- `docs/Flux_Fraude_MEROE_V6_4.md` : flux CODIR/DAF/DSI de l'alerte au cash.
- `docs/api_meroe_seeg_v1.yaml` : specification OpenAPI cible SEEG / MEROE.
- `docs/grille_fraude_seeg.csv` : codes fraude et baremes PV HT.
- `scripts/sandbox_meroe_fraud_flow.py` : simulation locale des 3 cas test.
- `scripts/demo_fraud_data.py` : fausses donnees completes visibles dans le dashboard.
- `docs/Architecture_Projet_MEROE.md` : schema global et competences demontrees.

Le message partenaire devient donc double :

1. SEEG Protect couvre deja le MVP d'alerte preventive et de suivi partenaire.
2. MEROE V6.4 prepare la boucle fraude : scanner EDAN, Liste Rouge, statut
   compteur, webhook de reactivation, bordereau DAF et success fee 5%.

## Securite minimale

Avant partage externe, definir un token admin :

```powershell
$env:SEEG_PROTECT_ADMIN_TOKEN="changer-ce-token"
python -m seeg_protect.app
```

Les partenaires accederont ensuite aux pages avec :

```text
https://votre-domaine/dashboard?token=changer-ce-token
https://votre-domaine/roadmap?token=changer-ce-token
```

## Donnees de demonstration

Pour alimenter la demo :

```powershell
python scripts\demo_api_flow.py
python scripts\demo_fraud_data.py
```

Le script cree :

1. une souscription ;
2. un paiement ;
3. une activation ;
4. une alerte faible ;
5. un SMS simule ;
6. un doublon bloque par l'anti-spam.
7. des compteurs fictifs fraude ;
8. des dossiers Liste Rouge ;
9. des statuts `COUPE` / `REACTIVE` ;
10. la success fee MEROE 5% ;
11. une alerte audit si reactivation sans motif paiement.

## Pre-requis avant vraie mise en ligne

- Choisir un hebergement pilote.
- Activer HTTPS.
- Definir `SEEG_PROTECT_ADMIN_TOKEN`.
- Definir `SEEG_PROTECT_WEBHOOK_SECRET`.
- Decider si SQLite suffit pour le pilote ou si PostgreSQL est requis.
- Choisir le fournisseur SMS reel.
- Valider le format exact des webhooks SEEG/EDAN.
- Valider avec la DSI le principe read-only pour le statut EDAN.
- Valider avec la DAF le bordereau mensuel Liste Rouge et la success fee 5%.
- Figer la grille fraude SEEG utilisee par `docs/grille_fraude_seeg.csv`.
- Confirmer que les flux standards restent anonymises : pas de nom client, pas
  de telephone client, pas de PV huissier transmis a MEROE.

## Message partenaire

Cette version pilote permet deja de suivre le fonctionnement complet du MVP :
webhooks, activation, alerte preventive, SMS, anti-doublon, dashboard, fiche
compteur et suivi d'avancement. Les prochaines decisions concernent surtout
l'integration fournisseur SMS, l'hebergement et les donnees SEEG pilote.

Extension V6.4 : le projet integre aussi le cadre fraude MEROE, avec une logique
simple pour le CODIR : `Data EDAN -> Terrain SEEG -> Cash DAF`. MEROE ne demande
pas d'acces en ecriture et ne recupere pas la donnee personnelle client ; la
facturation repose sur les statuts EDAN, le bordereau DAF et une commission de
performance.
