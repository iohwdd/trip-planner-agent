try:
    import pymysql
except ImportError:  # pragma: no cover - available after dependency install
    pymysql = None

if pymysql is not None:  # pragma: no cover - exercised in app startup
    pymysql.install_as_MySQLdb()
