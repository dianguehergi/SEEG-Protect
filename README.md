# MEROE CORE

Plateforme pilote pour la SEEG : un portail unique, deux produits et un moteur.

Version cible : **MEROE CORE V3.2**.

- Rail 1 : PROTEC, prevention client et SMS pour les abonnes.
- Rail 2 : SCORING Fraude, Liste Rouge, qualification SEEG et facturation 10%
  uniquement sur recouvrement prouve.

Le pitch DG :

```text
Vous avez 1 portail. Vous gerez vos clients ET vous traquez les pertes.
Nous prenons 0 risque : si nous ne vous rapportons rien, vous ne nous payez rien.
```

## Demarrage

```powershell
python -m seeg_protect.app
```

L'API demarre par defaut sur :

```text
http://127.0.0.1:8000
```

## Endpoints MVP

- `GET /health` : supervision technique.
- `GET /events?limit=20` : derniers evenements techniques.
- `GET /subscriptions?limit=50` : dernieres souscriptions.
- `GET /payments?limit=50` : derniers paiements.
- `GET /notifications?limit=50` : derniers SMS/notifications.
- `GET /fraud-cases?limit=50` : dossiers fraude MEROE V6.4.
- `GET /sos-energy?limit=50` : avances SOS Energie et remboursements.
- `GET /meters?meter_id=...` : detail JSON d'un compteur.
- `GET /meter?meter_id=...` : fiche HTML d'un compteur.
- `GET /dashboards` : portail des tableaux de bord partenaires.
- `GET /dashboard` : tableau de bord local en HTML.
- `GET /architecture` : page d'explication du scenario et de l'architecture.
- `GET /process` : vue de bout en bout client, SEEG, simulation, fraude et dashboard.
- `GET /roadmap` : page de suivi projet pour partenaires.
- `POST /webhooks/subscriptions` : reception d'une demande de souscription.
- `POST /webhooks/payments` : confirmation de prelevement SEEG.
- `POST /webhooks/low-balance` : alerte de solde faible.
- `POST /webhooks/fraud-cases` : reception d'un dossier Liste Rouge fraude.
- `POST /webhooks/fraud-status` : mise a jour statut compteur fraude.
- `POST /webhooks/sos-energy` : demande d'avance SOS Energie.
- `POST /webhooks/sos-energy-repayments` : remboursement SOS Energie.

## MEROE CORE V3.2

Le cadrage combine est disponible ici :

- `docs/Architecture_Projet_MEROE.md` : architecture 1 plateforme / 2 rails.
- `docs/CDC_MEROE_CORE_V3_2.md` : cahier des charges combine DG.
- `docs/ANNEXE_TECH_MEROE_CORE_V3_2.md` : fichier J+1, PV, scoring, regle 10%.
- `docs/CDC_PROTEC_RELIEF_V2_5.md` : archive du cadrage PROTEC seul.
- `scripts/score_meroe_core_v32.py` : scoring fraude explicable V3.2.
- `scripts/ingest_seeg_v25.py` : ingestion CSV PROTEC legacy.
- `scripts/algo_protec.py` : moteur de prediction PROTEC legacy.

Commande scoring V3.2 :

```powershell
python scripts\score_meroe_core_v32.py DATA_SEEG_J1.csv
```

Format CSV V3.2 minimal :

```text
numero_compteur;index_n;index_n_1;conso;etat_sts;recharges;canal_paiement
1234567890;950;1000;0;COUVERCLE_OUVERT;2;AIRTEL
```

Commandes PROTEC legacy :

```powershell
python scripts\ingest_seeg_v25.py SEEG_PROTEC_J0_20261004.csv
python scripts\algo_protec.py
```

Format CSV PROTEC legacy :

```text
numero_compteur;date_achat;montant_f
1234567890;04/10/2026 08:31;5000
```

Variables Postgres optionnelles :

- `PROTEC_DB_HOST`
- `PROTEC_DB_PORT`
- `PROTEC_DB_NAME`
- `PROTEC_DB_USER`
- `PROTEC_DB_PASS`

Les endpoints `POST` exigent l'en-tete `X-SEEG-Signature`, calcule avec HMAC SHA-256
sur le corps brut de la requete.

## Archive MEROE fraude V6.4

Le projet contient aussi les anciens livrables V6.4 de cadrage fraude. Ils sont
conserves comme archive technique, mais le cadrage DG actuel est V3.2 avec une
regle de facturation a 10% sur recouvrement prouve.

- `docs/Flux_Fraude_MEROE_V6_4.md` : flux Data EDAN -> Terrain SEEG -> Cash DAF.
- `docs/api_meroe_seeg_v1.yaml` : OpenAPI cible pour Liste Rouge, statut EDAN,
  webhook de reactivation et bordereau DAF.
- `docs/grille_fraude_seeg.csv` : codes fraude SEEG et baremes PV HT.
- `scripts/sandbox_meroe_fraud_flow.py` : simulation des 3 cas sandbox.

Cette archive preparait l'industrialisation du scanner MEROE : score fraude,
statut compteur read-only, bordereau DAF et controles DAF/DSI.

## Exemple de signature

```powershell
python scripts/sign_payload.py '{"subscription_id":"sub-1","meter_id":"meter-1","phone_number":"+24100000000"}'
```

## Variables d'environnement

- `SEEG_PROTECT_HOST` : hote HTTP, defaut `127.0.0.1`.
- `SEEG_PROTECT_PORT` : port HTTP, defaut `8000`.
- `SEEG_PROTECT_DB` : chemin SQLite, defaut `data/seeg_protect.sqlite3`.
- `SEEG_PROTECT_EVENT_LOG` : log JSONL, defaut `logs/events.jsonl`.
- `SEEG_PROTECT_WEBHOOK_SECRET` : secret HMAC partage avec la SEEG.
- `SEEG_PROTECT_DAILY_AVERAGE_KWH` : consommation moyenne journaliere par defaut.
- `SEEG_PROTECT_SMS_SENDER` : nom expediteur affiche par le fournisseur SMS.
- `SEEG_PROTECT_SMS_PROVIDER` : `stub` pour simuler, `http` pour appeler un fournisseur SMS.
- `SEEG_PROTECT_SMS_API_URL` : URL HTTP du fournisseur SMS.
- `SEEG_PROTECT_SMS_API_TOKEN` : jeton transmis en `Authorization: Bearer ...`.
- `SEEG_PROTECT_SMS_TIMEOUT_SECONDS` : delai maximum de l'appel SMS.
- `SEEG_PROTECT_SMS_OUTBOX` : fichier des SMS simules, defaut `logs/sms_outbox.jsonl`.
- `SEEG_PROTECT_LOW_BALANCE_SMS_COOLDOWN_HOURS` : delai anti-doublon SMS par compteur, defaut `24`.
- `SEEG_PROTECT_ADMIN_TOKEN` : token optionnel pour proteger dashboard et endpoints de consultation.

## SMS reel

Par defaut, le projet utilise `SEEG_PROTECT_SMS_PROVIDER=stub` : aucun vrai SMS
n'est envoye, mais la notification est enregistree comme si elle etait mise en file.
Chaque SMS simule est aussi visible dans `logs/sms_outbox.jsonl`.

Pour brancher un fournisseur SMS HTTP, configure :

```powershell
$env:SEEG_PROTECT_SMS_PROVIDER="http"
$env:SEEG_PROTECT_SMS_API_URL="https://api.fournisseur-sms.example/messages"
$env:SEEG_PROTECT_SMS_API_TOKEN="votre-jeton-api"
$env:SEEG_PROTECT_SMS_SENDER="SEEG Protect"
```

Le service enverra un `POST` JSON au fournisseur avec :

```json
{
  "to": "+24100000000",
  "message": "SEEG Protect: ...",
  "sender": "SEEG Protect"
}
```

La reponse du fournisseur peut contenir `message_id`, `id` ou `reference`; cette valeur
sera conservee comme reference technique de l'envoi.

## Anti-doublon SMS

Pour eviter de spammer un client, le service n'envoie pas une nouvelle alerte SMS
si le meme compteur a deja recu une notification dans les dernieres 24 heures.
Ce delai se regle avec `SEEG_PROTECT_LOW_BALANCE_SMS_COOLDOWN_HOURS`.

## Securite dashboard

Par defaut, le dashboard reste ouvert pour faciliter la demo locale. Pour le proteger,
definis un token admin avant de demarrer l'API :

```powershell
$env:SEEG_PROTECT_ADMIN_TOKEN="mon-token-admin"
python -m seeg_protect.app
```

Ensuite, ouvre :

```text
http://127.0.0.1:8000/dashboard?token=mon-token-admin
```

Les endpoints de consultation acceptent aussi l'en-tete `X-Admin-Token`.

## Demo locale complete

Demarre l'API :

```powershell
python -m seeg_protect.app
```

Dans un autre terminal, lance le scenario de demonstration :

```powershell
python scripts\demo_api_flow.py
```

Puis ouvre le tableau de bord :

```text
http://127.0.0.1:8000/dashboards
http://127.0.0.1:8000/dashboard
```

Pour comprendre l'architecture et le scenario metier :

```text
http://127.0.0.1:8000/architecture
```

Pour suivre l'avancement projet :

```text
http://127.0.0.1:8000/roadmap
```

Pour voir la fiche d'un compteur genere par la demo, copie son `meter_id` puis ouvre :

```text
http://127.0.0.1:8000/meter?meter_id=api-meter-...
```

Pour tester la logique fraude V6.4 sans serveur externe :

```powershell
python scripts\sandbox_meroe_fraud_flow.py
```

Pour charger de fausses donnees completes dans SQLite et les voir dans le
dashboard :

```powershell
python scripts\demo_fraud_data.py
```

## Tests

```powershell
python -m unittest discover -s tests
```

## Mise en ligne

Voir :

```text
docs/Deploiement_en_ligne.md
docs/Mise_en_ligne_partenaires.md
docs/Architecture_Projet_MEROE.md
```
