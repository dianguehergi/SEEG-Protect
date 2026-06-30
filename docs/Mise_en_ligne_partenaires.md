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
```

Le script cree :

1. une souscription ;
2. un paiement ;
3. une activation ;
4. une alerte faible ;
5. un SMS simule ;
6. un doublon bloque par l'anti-spam.

## Pre-requis avant vraie mise en ligne

- Choisir un hebergement pilote.
- Activer HTTPS.
- Definir `SEEG_PROTECT_ADMIN_TOKEN`.
- Definir `SEEG_PROTECT_WEBHOOK_SECRET`.
- Decider si SQLite suffit pour le pilote ou si PostgreSQL est requis.
- Choisir le fournisseur SMS reel.
- Valider le format exact des webhooks SEEG/EDAN.

## Message partenaire

Cette version pilote permet deja de suivre le fonctionnement complet du MVP :
webhooks, activation, alerte preventive, SMS, anti-doublon, dashboard, fiche
compteur et suivi d'avancement. Les prochaines decisions concernent surtout
l'integration fournisseur SMS, l'hebergement et les donnees SEEG pilote.
