"""
Root conftest — patch sqlite3 for ChromaDB on systems with sqlite < 3.35.
Must run before any crewai/chromadb imports.
"""

try:
    __import__("pysqlite3")
    import sys
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass  # pysqlite3 not installed; hope system sqlite3 is new enough
