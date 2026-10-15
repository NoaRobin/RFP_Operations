-- Dernière VL connue à la date d'arrêté, pour chaque part.
-- Tables et colonnes : voir catalog/fabric_catalog.md
SELECT
    a.CODE_ISIN_PART,
    a.NOM_PART,
    a.DEVISE_VL,
    a.DATE_VL,
    a.VL_UNITAIRE,
    a.NOMBRE_PARTS,
    a.ACTIF_NET_DEVISE_PART,
    a.ACTIF_NET_PART_EURO,
    a.ACTIF_NET_TOTAL_EURO,
    a.NOM_BENCH
FROM dbo.JUMP_portfolio_aum a
JOIN (
    SELECT CODE_ISIN_PART, MAX(DATE_VL) AS d
    FROM dbo.JUMP_portfolio_aum
    WHERE DATE_VL <= :as_of
    GROUP BY CODE_ISIN_PART
) m ON m.CODE_ISIN_PART = a.CODE_ISIN_PART AND m.d = a.DATE_VL
WHERE (:fonds IS NULL OR a.ID_JUMP_FONDS = :fonds)
ORDER BY a.ACTIF_NET_TOTAL_EURO DESC, a.ACTIF_NET_PART_EURO DESC
