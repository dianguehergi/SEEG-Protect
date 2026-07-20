# Cahier des charges technique - SEEG PROTEC Relief V2.5

Version : 2.5  
Date : 04/10/2026  
Budget dev : 1 500 000 FCFA HT  
Statut : archive du rail PROTEC seul

> Note V3.2 : ce document reste utile pour le detail PROTEC, mais le cadrage a
> presenter au DG est `MEROE CORE V3.2` : une seule plateforme, PROTEC + SCORING,
> avec priorite business sur le scoring fraude.

## 1. Objectif

Livrer en J+21 une plateforme Cloud qui analyse un fichier CSV SEEG et envoie
deux SMS par mois et par client a 250 FCFA, afin de reduire les coupures prepaid.

Contrainte structurante : 0 API EDAN, 0 seuil temps reel, 0 intervention DSI pour
le pilote.

## 2. Stack technique

| Brique | Choix |
| --- | --- |
| Backend | Python 3.11 + FastAPI |
| Jobs | Celery + Redis |
| Base | PostgreSQL 15 Cloud |
| Hebergement | VPS OVH/AWS 4GB RAM |
| SMS | API A2P Airtel/Moov Business |
| Expediteur | Ligne 068XXXXX, libelle SEEG PROTEC |
| Cout SMS | 20 FCFA HT / SMS |

## 3. Modules a developper

### M1. Ingestion CSV J0

Input :

```text
numero_compteur;date_achat;montant_f
```

Regles :

- garder les 12 derniers achats par client ;
- supprimer les doublons ;
- bloquer le fichier si plus de 5% des lignes sont invalides ;
- produire un rapport d'erreurs CSV.

### M2. Moteur algo V2.5

Formules :

```text
Nb_Jours_Moyen = MOYENNE(Date_Achat[n] - Date_Achat[n-1])
Conso_Jour = Montant_Moyen / Nb_Jours_Moyen
Date_J0 = Dernier_Achat + Nb_Jours_Moyen
Date_J-2 = Date_J0 - 2 jours
Montant_Conseille = Montant_Moyen
```

Boucle entrante :

- si SMS `RECHARGE 5000` recu, enregistrer le montant et recalculer le cycle du
  client immediatement.

### M3. Planning SMS

- Cron J-2 : 10h00 Africa/Libreville ;
- Cron J0 : 10h00 Africa/Libreville ;
- STOP : blacklist immediate ;
- maximum 2 SMS par client et par mois dans le pilote.

### M4. Gateway SMS

- API REST Airtel/Moov ;
- log DLR succes/echec pour chaque SMS ;
- debit cible : 50 000 SMS en moins de 2h.

### M5. Admin DCOM 1 ecran

KPIs :

- clients actifs ;
- SMS envoyes ce mois ;
- taux STOP ;
- cash SEEG 30% ;
- cout SMS ;
- marge estimee.

Actions :

- Upload CSV ;
- Pause Campagne ;
- Kill Switch Total.

## 4. Contenu SMS

SMS J-2 :

```text
SEEG PROTEC : M. [NOM] Base sur votre conso, rechargez sous 48h pour eviter la coupure. Prochain montant conseille : [MONTANT]F. STOP 068XXXXX
```

SMS J0 :

```text
SEEG PROTEC : ALERTE M. [NOM] Risque de coupure aujourd'hui. Rechargez maintenant. Agence : [VILLE]. STOP 068XXXXX
```

## 5. Exigences

| Sujet | Exigence |
| --- | --- |
| Capacite | 100 000 clients |
| CNPD | 0 solde, 0 kWh, uniquement date + montant |
| Securite | DB chiffree en production |
| Audit | Logs 100% tracables pour DCOM |
| Hors scope | API EDAN, paiement, application mobile |

## 6. Planning et livrables

| Echeance | Livrable |
| --- | --- |
| J+7 | M1 + M2 + test 100 compteurs fake |
| J+14 | M3 + M4 + premier SMS reel |
| J+21 | M5 + UAT 1 000 clients + doc admin 2 pages |

## Commande M1

```powershell
python scripts\ingest_seeg_v25.py SEEG_PROTEC_J0_20261004.csv
```

## Commande M2

```powershell
python scripts\algo_protec.py
```

Le script lit `clients_histo`, calcule `date_j0`, `date_jm2` et
`montant_conseille`, puis met la base a jour. Les colonnes sont creees
automatiquement si elles n'existent pas encore :

```sql
ALTER TABLE clients_histo
ADD COLUMN IF NOT EXISTS date_j0 DATE,
ADD COLUMN IF NOT EXISTS date_jm2 DATE,
ADD COLUMN IF NOT EXISTS montant_conseille INT;
```

## Chaine complete M1 > M2 > M3

| Heure | Action |
| --- | --- |
| J0 08h00 | DCOM upload CSV, puis `python scripts\ingest_seeg_v25.py fichier.csv` |
| J0 08h05 | `python scripts\algo_protec.py` |
| J-2 10h00 | Cron Celery lance M3 SMS 1 |
| J0 10h00 | Cron Celery lance M3 SMS 2 |

Statut : M1 et M2 prets a integrer. M3 SMS a coder ensuite.
