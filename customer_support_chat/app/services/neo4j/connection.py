# neo4j/connection.py - Neo4j connection management

from neo4j import GraphDatabase
from typing import Optional
import os

class Neo4jConnection:
    _instance: Optional["Neo4jConnection"] = None
    _driver = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._driver is None:
            uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            user = os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD", "password")
            try:
                self._driver = GraphDatabase.driver(uri, auth=(user, password))
            except Exception as e:
                print(f"Neo4j connection failed: {e}")
                self._driver = None

    @property
    def driver(self):
        return self._driver

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    def is_connected(self) -> bool:
        if self._driver is None:
            return False
        try:
            self._driver.verify_connectivity()
            return True
        except:
            return False

    def run_query(self, query: str, params: dict = None):
        """Execute a Cypher query and return results"""
        if not self._driver:
            raise ConnectionError("Neo4j driver not initialized")
        with self._driver.session() as session:
            result = session.run(query, params or {})
            return list(result)


_neo4j_conn = Neo4jConnection()


def get_neo4j() -> Neo4jConnection:
    return _neo4j_conn
