# Deploiement en ligne - SEEG Protect

## Objectif

Mettre en ligne SEEG Protect pour permettre aux partenaires de suivre :

- le portail partenaires ;
- le dashboard operationnel ;
- la roadmap projet ;
- l'architecture ;
- les fiches compteurs ;
- les donnees de demonstration.

## URLs importantes

Une fois en ligne, les pages principales seront :

```text
https://votre-domaine/dashboards
https://votre-domaine/dashboard
https://votre-domaine/roadmap
https://votre-domaine/architecture
https://votre-domaine/health
```

Si `SEEG_PROTECT_ADMIN_TOKEN` est defini, utiliser :

```text
https://votre-domaine/dashboards?token=VOTRE_TOKEN
```

## Deploiement recommande : Render

Le projet contient deja :

- `Dockerfile`
- `.dockerignore`
- `render.yaml`

Etapes :

1. Creer un depot GitHub avec le projet.
2. Pousser le code sur GitHub.
3. Aller sur Render.
4. Creer un nouveau service depuis le depot.
5. Choisir le deploiement via Docker.
6. Verifier les variables d'environnement.
7. Deployer.

Variables importantes :

```text
SEEG_PROTECT_HOST=0.0.0.0
SEEG_PROTECT_PORT=8000
SEEG_PROTECT_DB=/app/data/seeg_protect.sqlite3
SEEG_PROTECT_EVENT_LOG=/app/data/events.jsonl
SEEG_PROTECT_SMS_OUTBOX=/app/data/sms_outbox.jsonl
SEEG_PROTECT_WEBHOOK_SECRET=<secret fort>
SEEG_PROTECT_ADMIN_TOKEN=<token partenaire>
SEEG_PROTECT_SMS_PROVIDER=stub
```

Pour le pilote, `SEEG_PROTECT_SMS_PROVIDER=stub` est acceptable. Le SMS reel
viendra ensuite avec le fournisseur SMS choisi.

## Test apres deploiement

Verifier :

```text
GET /health
GET /dashboards?token=...
GET /dashboard?token=...
GET /roadmap?token=...
GET /architecture?token=...
```

Pour alimenter une demo distante, il faudra adapter `scripts/demo_api_flow.py`
avec l'URL publique du serveur au lieu de `127.0.0.1`.

## Points a ne pas oublier avant partage partenaire

- Ne pas partager un dashboard sans token admin.
- Changer `SEEG_PROTECT_WEBHOOK_SECRET`.
- Garder le mode SMS en `stub` tant que le fournisseur n'est pas valide.
- Tester `/health` apres chaque mise en ligne.
- Conserver une sauvegarde de `/app/data/seeg_protect.sqlite3`.

## Limite du pilote

SQLite suffit pour un pilote et une demonstration. Pour une vraie production
multi-utilisateur avec donnees SEEG volumineuses, prevoir PostgreSQL.
