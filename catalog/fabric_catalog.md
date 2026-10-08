# Catalogue Fabric — source de vérité

> Généré à partir de `catalog/fabric_schema.csv` (export `INFORMATION_SCHEMA.COLUMNS` du SQL endpoint).
> **Toute information marquée « À CONFIRMER » est une déduction** (nom de colonne, cohérence des types, usages métier) et doit être validée par l'équipe avant d'être considérée comme acquise.
> Les noms de tables et de colonnes ci-dessous sont, eux, **certains** : ils proviennent directement de l'export.

## Vue d'ensemble

| Élément | Valeur |
|---|---|
| Lakehouse (base) | `LKH_RFPTeam_Bronze` |
| Schéma | `dbo` |
| Couche | Bronze (données brutes chargées depuis JUMP) — *provenance JUMP déduite du préfixe et des scripts existants : À CONFIRMER* |
| Nombre de tables | 5 (2 JUMP + 3 Product Info) |
| Contraintes déclarées | Aucune (tables Delta d'un Lakehouse : ni clé primaire ni clé étrangère n'existent physiquement). Toutes les clés ci-dessous sont **déduites**. |
| Nullabilité | Toutes les colonnes acceptent `NULL`. |
| Chaînes | `varchar(8000)` partout : mapping standard du SQL endpoint Fabric pour les colonnes `string` Delta (aucune longueur métier n'est imposée). |

Référence SQL complète d'une table : `[LKH_RFPTeam_Bronze].[dbo].[<table>]` (ou `dbo.<table>` depuis le SQL endpoint du Lakehouse).

---

## 1. `dbo.JUMP_portfolio_aum`

**Description métier (déduite — À CONFIRMER)** : encours (AUM) et valeur liquidative par **part** de fonds et par **date de VL**. Une ligne = une part (classe d'action) d'un fonds à une date de valorisation, avec ses actifs nets exprimés en devise de la part, en devise du fonds et en euro, ainsi que le niveau de l'indice de référence et les éventuels dividendes.

**Grain / clé (déduit — À CONFIRMER)** : (`ID_JUMP_PART`, `DATE_VL`). `CODE_ISIN_PART` + `DATE_VL` est probablement aussi unique.

| # | Colonne | Type | Signification (déduite) |
|---|---|---|---|
| 1 | `ID_JUMP_FONDS` | varchar(8000) | Identifiant interne JUMP du fonds. Clé de jointure vers `JUMP_portfolio_holdings` — À CONFIRMER |
| 2 | `ID_PI_FONDS` | varchar(8000) | Identifiant du fonds dans un second référentiel (« PI » : signification À CONFIRMER) |
| 3 | `ID_JUMP_PART` | varchar(8000) | Identifiant interne JUMP de la part |
| 4 | `ID_PI_PART` | varchar(8000) | Identifiant de la part dans le référentiel « PI » — À CONFIRMER |
| 5 | `CODE_ISIN_PART` | varchar(8000) | Code ISIN de la part. Clé naturelle utilisée dans les questionnaires RFP |
| 6 | `NOM_PART` | varchar(8000) | Libellé de la part |
| 7 | `DATE_VL` | date | Date de la valeur liquidative |
| 8 | `VL_UNITAIRE` | decimal(14,5) | Valeur liquidative d'une part, en `DEVISE_VL` |
| 9 | `NOMBRE_PARTS` | decimal(13,4) | Nombre de parts en circulation de la part |
| 10 | `NOMBRE_PARTS_FONDS` | decimal(13,4) | Nombre total de parts du fonds (toutes parts confondues) — À CONFIRMER |
| 11 | `DEVISE_VL` | varchar(8000) | Devise de cotation de la part (code ISO 4217 attendu — À CONFIRMER) |
| 12 | `ACTIF_NET_DEVISE_PART` | decimal(14,2) | Actif net de la part, en devise de la part |
| 13 | `COEFFICIENT_OST` | decimal(5,2) | Coefficient d'ajustement lié à une opération sur titres (division, regroupement) — À CONFIRMER |
| 14 | `DEVISE_FONDS` | varchar(8000) | Devise de référence du fonds |
| 15 | `ACTIF_NET_PART_DEVISE_FONDS` | decimal(14,2) | Actif net de la part, converti en devise du fonds |
| 16 | `ACTIF_NET_TOTAL_DEVISE_FONDS` | decimal(14,2) | Actif net total du fonds, en devise du fonds (répété sur chaque part du fonds — À CONFIRMER) |
| 17 | `NOM_BENCH` | varchar(8000) | Nom de l'indice de référence |
| 18 | `VL_BENCH` | decimal(14,5) | Niveau de l'indice de référence à `DATE_VL` |
| 19 | `DIVIDEND_AMOUNT` | decimal(13,4) | Montant du dividende détaché (par part — À CONFIRMER) |
| 20 | `DIVIDEND_DEVISE` | varchar(8000) | Devise du dividende |
| 21 | `ACTIF_NET_TOTAL_EURO` | decimal(14,2) | Actif net total du fonds, en euro |
| 22 | `ACTIF_NET_PART_EURO` | decimal(14,2) | Actif net de la part, en euro |
| 23 | `DATE_MAJ` | datetime2 | Horodatage de chargement / mise à jour de la ligne (technique) |

> ⚠️ **Précision numérique** : `decimal(14,2)` plafonne à 999 999 999 999,99. Suffisant pour des encours en euros, mais à garder en tête pour des devises à faible valeur unitaire (JPY, etc.) — À CONFIRMER.
> ⚠️ Pas de colonne « nom du fonds » dans cette table : le nom du fonds se trouve dans `JUMP_portfolio_holdings.NOM_FONDS`.

---

## 2. `dbo.JUMP_portfolio_holdings`

**Description métier (déduite — À CONFIRMER)** : inventaire des portefeuilles. Une ligne = une position (instrument) détenue par un fonds à une date d'inventaire, avec quantités, cours, montants, expositions et poids.

**Grain / clé (déduit — À CONFIRMER)** : (`ID_JUMP_FONDS`, `DATE_INVENTAIRE`, `ID_JUMP_INSTRUMENT`, `TYPE_HOLDING`). Un même instrument pourrait apparaître sur plusieurs lignes (types de holding différents, dérivés, etc.).

| # | Colonne | Type | Signification (déduite) |
|---|---|---|---|
| 1 | `ID_JUMP_FONDS` | varchar(8000) | Identifiant interne JUMP du fonds |
| 2 | `ID_PI_FONDS` | varchar(8000) | Identifiant du fonds dans le référentiel « PI » — À CONFIRMER |
| 3 | `NOM_FONDS` | varchar(8000) | Libellé du fonds |
| 4 | `DEVISE_FONDS` | varchar(8000) | Devise de référence du fonds |
| 5 | `DATE_INVENTAIRE` | date | Date de l'inventaire |
| 6 | `DATE_COTATION` | date | Date du cours utilisé pour valoriser la ligne |
| 7 | `ID_JUMP_INSTRUMENT` | varchar(8000) | Identifiant interne JUMP de l'instrument |
| 8 | `CODE_ISIN_INSTRUMENT` | varchar(8000) | Code ISIN de l'instrument (vide possible pour cash, dérivés OTC… — À CONFIRMER) |
| 9 | `CODE_BLOOMBERG` | varchar(8000) | Ticker Bloomberg de l'instrument |
| 10 | `CODE_AIM_FONDS` | varchar(8000) | Code du fonds dans un système « AIM » (signification À CONFIRMER) |
| 11 | `NOM_INSTRUMENT` | varchar(8000) | Libellé de l'instrument |
| 12 | `DEVISE_INSTRUMENT` | varchar(8000) | Devise de cotation de l'instrument |
| 13 | `CODE_TYPE_INSTRUMENT` | varchar(8000) | Code du type d'instrument (nomenclature JUMP — À CONFIRMER) |
| 14 | `CLASSE_ACTIF` | varchar(8000) | Classe d'actifs (actions, obligations, monétaire… — valeurs À CONFIRMER) |
| 15 | `TYPE_HOLDING` | varchar(8000) | Nature de la ligne (titre, cash, dérivé… — valeurs À CONFIRMER) |
| 16 | `QUANTITE` | decimal(16,4) | Quantité détenue |
| 17 | `QUANTITE_JUMP` | decimal(16,4) | Quantité telle que calculée/retraitée par JUMP — différence avec `QUANTITE` À CONFIRMER |
| 18 | `POIDS_LIGNE_EXPO` | decimal(8,5) | Poids de la ligne en exposition (fraction ou pourcentage : **À CONFIRMER**) |
| 19 | `POIDS_LIGNE_TAUX` | decimal(8,5) | Poids de la ligne dans la poche taux / contribution taux — À CONFIRMER |
| 20 | `COURS_UNITAIRE` | decimal(16,4) | Cours unitaire en devise de l'instrument |
| 21 | `MONTANT_DEVISE_INSTRUMENT` | decimal(16,4) | Valeur de marché de la ligne en devise de l'instrument |
| 22 | `MONTANT_DEVISE_FONDS` | decimal(16,4) | Valeur de marché de la ligne en devise du fonds |
| 23 | `EXPOSITION_DEVISE_INSTRUMENT` | decimal(16,4) | Exposition (notionnel/équivalent sous-jacent) en devise de l'instrument — À CONFIRMER |
| 24 | `EXPOSITION_DEVISE_FONDS` | decimal(16,4) | Exposition en devise du fonds — À CONFIRMER |
| 25 | `PRU_DEVISE_FONDS` | decimal(16,4) | Prix de revient unitaire, en devise du fonds |
| 26 | `TYPE_DETTE` | varchar(8000) | Type de dette pour les instruments de taux (senior, subordonnée… — À CONFIRMER) |
| 27 | `COUPON_COURU_PERC` | decimal(16,6) | Coupon couru en % du nominal |
| 28 | `COURS_UNITAIRE_PERC` | decimal(16,4) | Cours exprimé en % du nominal (obligations) |
| 29 | `TAUX_CHANGE_EUR` | decimal(16,6) | Taux de change de la devise de l'instrument vers l'euro (sens de cotation À CONFIRMER) |
| 30 | `DATE_MAJ` | datetime2 | Horodatage de chargement / mise à jour de la ligne (technique) |

---

## 3. Tables Product Info (`pi_out_product_active`, `PI_OUT_Share`, `PI_OUT_CountryOfRegistration`)

Ajoutées d'après le `schema.json` d'App4everyone (longueurs non fournies → `NULL` ; nullabilité supposée `YES` : **À CONFIRMER**).

| Table | Colonnes | Grain (déduit — À CONFIRMER) | Clé (déduite — À CONFIRMER) |
|---|---|---|---|
| `dbo.pi_out_product_active` | 434 | une ligne = un fonds actif | `pi_productid` (= `JUMP_*.ID_PI_FONDS`) |
| `dbo.PI_OUT_Share` | 284 | une ligne = une part | `pi_shareid` (= `JUMP_portfolio_aum.ID_PI_PART`) ; `ISIN_Code` ; lien fonds via `ProductID` |
| `dbo.PI_OUT_CountryOfRegistration` | 14 | une ligne = un pays d'enregistrement d'une part | — |

Colonnes utilisées par le remplissage de RFI (dictionnaire `backend/merlin/rfi/facts.yaml`) :
- **Fonds** : `Product_Name`, `Legal_Form`, `Domiciliation`, `Umbrella_Name`, `Applicable_UCI_Regulation`, `Creation_Date`, `Accounting_Currency`, `LEI_Code`, `Asset_Class`, `Investment_Zone`, `AMF_Classification`, `Fund_Range`, `Maturity_date`, `Official_Risk_Scale`, `Official_Risk_Scale_SRRI`, `ESG_SFDR_Article`, `ESG_AMF_Category`, labels (`Finansol_Label`, `Belgium_Towards_Sustainability_label`…), `Volatility_target`, `Recommended_Investment_Period`, `Portfolio_Manager`, `Portfolio_Manager_backup_1`, `Start_date_Portfolio_manager`, `Depositary`, `Custodian`, `Fund_Administrator`, `Commissaire_Aux_Comptes`, `Transfer_Agent`, `Centralizing_Agent`, `NAV_Frequency`, `Max_management_fee_PerCent`, `Performance_fees`, `High_Water_Mark`, `Gips_Compliance`, `Benchmark_Name`.
- **Part** : `Share_Name`, `ISIN_Code`, `Subscription_Currency`, `Creation_Date`, `First_NAV_Date`, `Initial_NAV`, `Initial_Subscription_Minimum_Amount`, `Actual_Financial_Management_Fees`, `Max_Financial_Management_Fees`, `Ongoing_Charges_ex_post`, `Ongoing_Charges_ex_ante`, `Maximum_Subscription_Fee_Rate_Not_Retained`, `Maximum_Redemption_Fee_Rate_Not_Retained`, cut-offs et règlements, `Income_Distribution`, `Distribution_Frequency`, `Bloomberg_Ticker`, `Morningstar_rating`, `Investor_Type`, `Share_Hedged_Against_FX_Exposure`, `Swing_Pricing`, `Gate`, `TER_Max`, `Wkn_Number`, `Sedol_Code`, `Swiss_Valor_Number`.

**Unités À CONFIRMER** : les taux (frais, frais courants) sont-ils stockés en fraction (0,015) ou en pourcentage (1,5) ? Le moteur RFI considère qu'une valeur ≤ 0,05 est une fraction.

---

## Relations (toutes déduites — À CONFIRMER)

```
JUMP_portfolio_aum (n parts × n dates)          JUMP_portfolio_holdings (n lignes × n dates)
 ├── ID_JUMP_FONDS  ───────────────────────────►  ID_JUMP_FONDS
 ├── ID_PI_FONDS    ───────────────────────────►  ID_PI_FONDS
 └── DATE_VL        ··· (alignement possible) ···  DATE_INVENTAIRE
```

| De | Vers | Cardinalité | Statut |
|---|---|---|---|
| `JUMP_portfolio_aum.ID_JUMP_FONDS` | `JUMP_portfolio_holdings.ID_JUMP_FONDS` | n parts ↔ n lignes (via le fonds) | À CONFIRMER |
| `JUMP_portfolio_aum.ID_PI_FONDS` | `JUMP_portfolio_holdings.ID_PI_FONDS` | idem | À CONFIRMER |
| `JUMP_portfolio_aum.DATE_VL` | `JUMP_portfolio_holdings.DATE_INVENTAIRE` | une VL par date d'inventaire ? | À CONFIRMER (les dates d'inventaire peuvent être mensuelles et les VL quotidiennes) |
| `JUMP_portfolio_aum.DEVISE_FONDS` | `JUMP_portfolio_holdings.DEVISE_FONDS` | redondance attendue | À CONFIRMER |

## Usages dans Merlin

| Usage | Tables / colonnes |
|---|---|
| Automatisation `aum_par_part` (encours d'une date) | `JUMP_portfolio_aum` : `CODE_ISIN_PART`, `NOM_PART`, `DATE_VL`, `VL_UNITAIRE`, `DEVISE_VL`, `ACTIF_NET_PART_EURO`, `ACTIF_NET_TOTAL_EURO`, `NOM_BENCH` |
| Automatisation `top_lignes_portefeuille` | `JUMP_portfolio_holdings` : `NOM_FONDS`, `DATE_INVENTAIRE`, `CODE_ISIN_INSTRUMENT`, `NOM_INSTRUMENT`, `CLASSE_ACTIF`, `DEVISE_INSTRUMENT`, `MONTANT_DEVISE_FONDS`, `POIDS_LIGNE_EXPO` |
| Extractions de l'Atelier Excel | voir `backend/merlin/atelier/extractions.yaml` |
| Remplissage de RFI (Excel / Word) | Product Info (≈ 90 %) + JUMP (encours, VL, lignes) : voir `backend/merlin/rfi/facts.yaml` |

## Questions ouvertes pour l'équipe

1. Que désigne le préfixe **PI** (`ID_PI_FONDS`, `ID_PI_PART`) ? Et **AIM** (`CODE_AIM_FONDS`) ?
2. `POIDS_LIGNE_EXPO` / `POIDS_LIGNE_TAUX` : fraction (0,0523) ou pourcentage (5,23) ?
3. Fréquence des `DATE_VL` (quotidienne ?) et des `DATE_INVENTAIRE` (mensuelle ?).
4. Existe-t-il des couches Silver/Gold avec des tables nettoyées (référentiel fonds, performances) ?
5. Valeurs possibles de `CLASSE_ACTIF`, `TYPE_HOLDING`, `CODE_TYPE_INSTRUMENT`, `TYPE_DETTE`.
