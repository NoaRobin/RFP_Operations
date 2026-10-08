from merlin.config import get_settings
from merlin.data.access import build_data_access, named_to_qmark
from merlin.data.catalog import load_catalog
from merlin.data.mock import isin_check_digit


def catalog():
    return load_catalog(str(get_settings().catalog_csv))


def test_catalog_has_two_tables():
    tables = catalog().tables
    assert {"JUMP_portfolio_aum", "JUMP_portfolio_holdings", "PI_OUT_Share", "pi_out_product_active"} <= set(tables)
    assert len(tables["JUMP_portfolio_aum"].columns) == 23
    assert len(tables["JUMP_portfolio_holdings"].columns) == 30


def test_validation_rejects_unknown_names():
    problems = catalog().validate_sql("SELECT a.FOO FROM dbo.JUMP_portfolio_aum a")
    assert any("FOO" in p for p in problems)
    problems = catalog().validate_sql("SELECT 1 FROM dbo.jump_portfolio_aum")
    assert any("sensible à la casse" in p for p in problems)


def test_validation_accepts_ctes_and_aliases():
    sql = """WITH x AS (SELECT CODE_ISIN_PART, MAX(DATE_VL) AS d FROM dbo.JUMP_portfolio_aum GROUP BY CODE_ISIN_PART)
             SELECT x.CODE_ISIN_PART, x.d FROM x ORDER BY d"""
    assert catalog().validate_sql(sql) == []


def test_named_params_conversion():
    sql, values = named_to_qmark("SELECT ':pas_un_param' WHERE a = :x OR (:y IS NULL OR b = :y)", {"x": 1, "y": None})
    assert sql == "SELECT ':pas_un_param' WHERE a = ? OR (? IS NULL OR b = ?)"
    assert values == [1, None, None]


def test_mock_isins_are_fictional_and_valid():
    data = build_data_access("mock")
    frame = data.query("SELECT DISTINCT CODE_ISIN_PART AS k FROM dbo.JUMP_portfolio_aum")
    assert len(frame) > 10
    for isin in frame["k"]:
        assert isin.startswith("QZ")
        assert isin_check_digit(isin[:-1]) == isin[-1]
