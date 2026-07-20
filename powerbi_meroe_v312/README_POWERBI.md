# Dashboard Pilote MÉROÉ V3.12 — Kit Power BI Desktop

Ce dossier fournit un dataset de démonstration anonymisé, les mesures DAX et le thème du dashboard pilote indépendant du dashboard DG SEEG.

## Démarrage dans Power BI Desktop

1. Exécuter `python scripts/build_powerbi_meroe_v312.py` depuis la racine du projet.
2. Dans Power BI Desktop : **Obtenir des données > Texte/CSV**, importer les huit CSV du dossier `data`.
3. Créer les relations : `dim_date[date]` vers les dates des cinq tables quotidiennes ; `flux_ia_anomalies[anomaly_id]` vers `flux_retour_seeg[anomaly_id]` (1:1) ; aucune relation client.
4. Marquer `dim_date` comme table de dates, puis trier `month` par `month_number` si nécessaire.
5. Importer `theme_meroe_v312.json` via **Affichage > Thèmes > Parcourir les thèmes**.
6. Créer une table `_Mesures`, puis recopier les mesures de `MEROE_V312_Mesures.dax` une par une.

## Pages 16:9 à construire

### 1 — LE TRÉSOR

- Bandeau filtres : période, canal, statut de paiement.
- Cartes : CA PROTEC Brut, CA PROTEC Net MÉROÉ, Commission IA, Total à recevoir, Impayés/Retard.
- Courbe : axe `dim_date[date]`, valeurs `CA PROTEC Brut` et `Commission IA`.
- Histogramme : Payé par AIRTEL vs Payé par SEEG.
- Alerte rouge si `Impayés / Retard > 0`.

### 2 — OPÉRATIONNEL PROTEC

- Cartes : Abonnés actifs, Nouvelles souscriptions, Désabonnements, SMS envoyés J-3, Taux délivrabilité, Appels, Taux recharge post-SMS.
- Entonnoir : `sent_j3` → `delivered` → `recharged_72h`.
- Courbe quotidienne souscriptions/désabonnements.
- Objectif visible : taux recharge post-SMS ≥ 35 %.

### 3 — IA ANOMALIES

- Cartes : Compteurs analysés, Anomalies IA, Fraudes qualifiées, Taux transformation, Potentiel détecté, Réellement recouvré.
- Barres Top 5 motifs par nombre d’anomalies.
- Barres Top 5 zones à risque par montant potentiel. Une carte remplie peut remplacer ce visuel lorsque les coordonnées fiables sont disponibles.
- Objectif visible : taux transformation > 20 %.

### 4 — ADMINISTRATIF & CONFORMITÉ

- Matrice : mois, document_type, status, invoice_amount_xaf.
- Cartes : Factures émises, Tickets litiges, dernier statut SFTP.
- Table d’audit : month, document_type, cndp_log_hash. Ne jamais afficher d’identifiant brut.
- Mise en forme conditionnelle : `KO` rouge, `ATTENDU` orange, `OK/RECU/EMISE` vert.

## Règles de gouvernance

- Aucune donnée nominative, aucun téléphone, aucun numéro de compteur brut.
- Les tables du kit n’exposent que des agrégats, zones et `meter_hash` irréversible de démonstration.
- En production, appliquer une sécurité par rôles et masquer les colonnes techniques.
- Afficher clairement la mention **DONNÉES DE DÉMONSTRATION** tant que les cinq flux réels ne sont pas raccordés.
- Conserver les justificatifs Airtel/SEEG hors du modèle public ; n’exposer que leur statut et leur empreinte.

## Branchements de production

Remplacer chaque CSV par sa source sans changer les noms de colonnes : API Airtel J+1, Excel guichets J+7, base SMS interne, base IA interne, Excel retour SEEG J+30. Utiliser Power Query pour typer les dates et montants, contrôler les doublons et rejeter toute colonne nominative.
