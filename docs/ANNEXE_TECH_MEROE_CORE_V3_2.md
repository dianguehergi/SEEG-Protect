# Annexe technique - MEROE CORE V3.2

## 1. Fichier SEEG J+1

Separateur recommande : point-virgule.

Colonnes minimales :

```text
numero_compteur;index_n;index_n_1;conso;etat_sts;recharges;canal_paiement
```

Colonnes recommandees :

```text
numero_compteur;nom_client;telephone;quartier;ville;date_releve;index_n;index_n_1;conso;conso_moyenne_90j;etat_sts;recharges;montant_recharge_30j;canal_paiement;statut_protec
```

## 2. Regles de validation

| Champ | Regle |
| --- | --- |
| `numero_compteur` | 10 a 12 chiffres |
| `index_n` | nombre positif |
| `index_n_1` | nombre positif |
| `conso` | nombre, peut etre 0 |
| `etat_sts` | valeur normalisee |
| `recharges` | entier >= 0 |
| `canal_paiement` | `GUICHET`, `AIRTEL`, `MOOV`, `AUTRE` |

Rejet fichier si :

- colonnes obligatoires absentes ;
- plus de 5% lignes invalides ;
- doublons compteur/date au-dessus d'un seuil a definir.

## 3. Scoring fraude V1 explicable

Le scoring doit rester simple pour le premier rendez-vous DG.

| Signal | Points |
| --- | ---: |
| Index N inferieur a Index N-1 | +35 |
| Consommation nulle avec recharge recente | +25 |
| Chute conso > 40% vs moyenne 90j | +25 |
| Etat STS anormal | +25 |
| Canal paiement atypique ou incoherent | +10 |
| Repetition anomalie | +15 |

Score final plafonne a 100.

Seuil Liste Rouge :

```text
score >= 80
```

Script demo :

```powershell
python scripts\score_meroe_core_v32.py DATA_SEEG_J1.csv
```

Sortie :

```text
Liste_Rouge_MEROE_CORE_V3_2.csv
```

## 4. Modele PV Liste Rouge J+5

Colonnes :

```text
pv_id;date_pv;numero_compteur;quartier;score;type_anomalie;montant_potentiel;priorite;statut
```

Statuts :

- `A_TRAITER` ;
- `EN_COURS_TERRAIN` ;
- `QUALIFIE_FRAUDE` ;
- `NON_FRAUDE` ;
- `CLOTURE`.

## 5. Modele PV Qualification J+15

Colonnes :

```text
pv_id;numero_compteur;statut_qualification;montant_recouvre;date_qualification;agent;commentaire
```

Regle :

- seul `statut_qualification = QUALIFIE_FRAUDE` avec `montant_recouvre > 0`
  declenche la facture MEROE.

## 6. Calcul facture 10%

```text
facture_meroe = montant_recouvre * 0.10
```

Exemple :

```text
montant_recouvre = 1 250 000 FCFA
facture_meroe = 125 000 FCFA
```

## 7. Profils et droits

| Profil | Acces |
| --- | --- |
| DG | lecture globale, export PV |
| Service Client | PROTEC, appels, historique SMS |
| Finance | repartition, ecarts, factures |
| Brigade Fraude | Liste Rouge, qualification, recouvrement |
| Admin MEROE | parametrage, import, supervision |

## 8. Points a valider avec la SEEG

1. Format exact du fichier J+1.
2. Definition officielle des etats STS.
3. Liste des quartiers pilote, dont Nzeng.
4. Regle exacte de repartition 30/70/16/2.
5. Processus officiel du PV Qualification.
6. Responsable SEEG qui valide le declenchement facture 10%.
