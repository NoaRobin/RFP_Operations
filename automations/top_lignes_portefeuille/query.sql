-- Top N lignes du dernier inventaire <= date d'arrêté, hors liquidités.
-- NB : l'unité de POIDS_LIGNE_EXPO (fraction ou %) est « À CONFIRMER » (catalogue).
WITH inv AS (
    SELECT MAX(DATE_INVENTAIRE) AS d
    FROM dbo.JUMP_portfolio_holdings
    WHERE ID_JUMP_FONDS = :fonds AND DATE_INVENTAIRE <= :as_of
)
SELECT TOP (:top_n)
    h.NOM_FONDS,
    h.DATE_INVENTAIRE,
    h.CODE_ISIN_INSTRUMENT,
    h.NOM_INSTRUMENT,
    h.CLASSE_ACTIF,
    h.DEVISE_INSTRUMENT,
    h.MONTANT_DEVISE_FONDS,
    h.POIDS_LIGNE_EXPO
FROM dbo.JUMP_portfolio_holdings h
JOIN inv ON h.DATE_INVENTAIRE = inv.d
WHERE h.ID_JUMP_FONDS = :fonds
  AND (h.TYPE_HOLDING IS NULL OR h.TYPE_HOLDING <> 'CASH')
ORDER BY h.MONTANT_DEVISE_FONDS DESC
