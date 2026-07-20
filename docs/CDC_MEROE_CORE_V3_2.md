# Cahier des charges - MEROE CORE V3.2

Version : 3.2  
Statut : pret pour cadrage DG SEEG  
Positionnement : 1 plateforme, 2 produits, 1 moteur

## 1. Objectif

MEROE CORE V3.2 fournit a la SEEG un portail unique pour :

- proteger les clients prepaid via PROTEC ;
- detecter les anomalies et pertes via SCORING Fraude ;
- suivre la repartition financiere ;
- fermer la boucle entre detection, qualification, recouvrement et facturation.

La priorite business V3.2 est le scoring fraude, car il parle directement au DG :
pertes detectees, cash recouvre, paiement MEROE uniquement sur resultat.

## 2. Alimentation unique SEEG J+1

La SEEG transmet un fichier unique pour 300 000 compteurs EDAN, correspondant
au parc SEEG a scorer.

Format cible :

```text
numero_compteur;index_n;index_n_1;conso;etat_sts;recharges;canal_paiement
```

Ce fichier alimente simultanement :

- le rail PROTEC pour les clients abonnes ;
- le rail SCORING pour tout le parc.

## 3. Produit 1 - PROTEC

Perimetre : base abonnes active transmise par la SEEG. Le chiffre de 5 000
abonnes sert uniquement d'hypothese de pilote et de dimensionnement demo ; ce
n'est pas une limite produit.

Objectif :

- prevenir les coupures ;
- rassurer le client ;
- reduire les reclamations ;
- generer une recette recurrente.

Regles :

- si conso ou recharge sous seuil, declencher SMS J-3 puis J-1 ;
- limiter a deux SMS par cycle ;
- gerer STOP immediatement ;
- conserver historique SMS et DLR.

Sorties :

- SMS client ;
- statut client `OK`, `ALERTE_J_3`, `URGENCE_J_1`, `COUPE` ;
- KPI Service Client et DG.

## 4. Produit 2 - SCORING Fraude

Perimetre initial : 300 000 compteurs EDAN, soit le parc SEEG.

Objectif :

- detecter les anomalies ;
- produire une Liste Rouge exploitable ;
- aider la Brigade Fraude a prioriser ;
- prouver le recouvrement ;
- facturer MEROE uniquement sur les montants qualifies.

Score :

| Score | Statut | Action |
| ---: | --- | --- |
| 0-49 | Normal | Aucun traitement |
| 50-79 | Surveillance | A suivre |
| 80-100 | Liste Rouge | Qualification terrain |

Signaux minimum :

- chute de consommation ;
- consommation nulle ;
- index incoherent ;
- etat STS anormal ;
- recharge ou canal atypique ;
- repetition d'anomalies.

## 5. Portail SEEG

Le portail contient 4 dashboards.

| Dashboard | Cible | But |
| --- | --- | --- |
| DG SEEG | Direction Generale | ROI global, pertes, cash, PROTEC |
| Service Client | DCOM / relation client | abonnes PROTEC, appels, SMS |
| Finance | DAF | repartition, ecarts, PV |
| Brigade Fraude | Terrain / controle | Liste Rouge, qualification, recouvrement |

## 6. Repartition et finance

Le dashboard Finance doit montrer :

- pot guichet ;
- pot Airtel ;
- repartition 30/70/16/2 ;
- ecarts ;
- anomalies de paiement ;
- exports PV.

Point a verrouiller avant contrat : definir clairement ce que representent
30/70/16/2, pour eviter une ambiguite entre SEEG, MEROE, operateurs, frais et
taxes.

## 7. Facturation MEROE 10%

Regle centrale :

```text
MEROE facture 10% uniquement sur les dossiers qualifies fraude par la SEEG
et associes a un montant recouvre ou valide.
```

La facturation ne se declenche pas sur :

- suspicion non traitee ;
- fausse alerte ;
- dossier sans qualification SEEG ;
- dossier qualifie sans montant recouvre.

## 8. Circuit ferme

| Jalons | Evenement |
| --- | --- |
| J+1 | SEEG pousse le fichier 300 000 compteurs EDAN |
| J+2 | MEROE calcule PROTEC et SCORING |
| J+3 | MEROE envoie SMS PROTEC |
| J+5 | MEROE transmet PV repartition + Liste Rouge |
| J+15 | SEEG renvoie PV qualification fraude |
| J+20 | MEROE facture 10% sur qualifies fraude recouvres |

## 9. Exigences techniques

- Python 3.11 ;
- ingestion CSV robuste ;
- base PostgreSQL 15 ;
- jobs planifies ;
- portail web securise ;
- logs auditables ;
- exports CSV/PDF ;
- droits par profil : DG, Service Client, Finance, Brigade Fraude ;
- aucune action de coupure par MEROE.

## 10. Criteres de succes pilote

Le pilote est reussi si la SEEG voit :

- une Liste Rouge intelligible ;
- des dossiers fraude qualifies ;
- un montant recouvre ;
- une facture MEROE calculee automatiquement ;
- une vue client PROTEC operationnelle ;
- un portail suffisamment clair pour le DG, Finance et Terrain.
