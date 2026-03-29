"""
KnowledgeGraph — KuzuDB embedded graph for IPL Oracle.

Schema:
  Nodes: Team, Player, Venue
  Edges: PlaysFor (Player→Team), PlayedAt (Player→Venue), Matchup (Player→Player)

Provides: setup_schema(), query(), seed helpers, close().
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import kuzu

from app.config.settings import settings

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """
    Embedded KuzuDB knowledge graph for IPL match entities.

    Usage:
        graph = KnowledgeGraph()
        graph.setup_schema()
        results = graph.query("MATCH (p:Player) RETURN p.name LIMIT 5")
        graph.close()
    """

    def __init__(self, db_path: str | None = None) -> None:
        """
        Initialise KuzuDB connection.

        Args:
            db_path: Path to KuzuDB database directory.
                     Defaults to settings.kuzu_db_path.
        """
        path = db_path or settings.kuzu_db_path
        db_dir = Path(path)
        db_dir.mkdir(parents=True, exist_ok=True)

        self._db = kuzu.Database(str(db_dir))
        self._conn = kuzu.Connection(self._db)
        logger.info("KuzuDB connected at %s", db_dir.resolve())

    # ------------------------------------------------------------------
    # Schema setup
    # ------------------------------------------------------------------

    def setup_schema(self) -> None:
        """
        Create all node and relationship tables if they don't exist.

        Schema:
          Team: id STRING PK, name STRING, home_venue STRING, home_city STRING
          Player: id STRING PK, name STRING, team STRING, role STRING,
                  is_foreign BOOLEAN, batting_style STRING, bowling_style STRING
          Venue: id STRING PK, name STRING, city STRING, capacity INT64,
                 avg_first_innings_score INT64
          Matchup: Player → Player (REL), balls INT64, runs INT64, wickets INT64, dots INT64
          PlayedAt: Player → Venue (REL), innings INT64, runs INT64, avg DOUBLE, sr DOUBLE
          PlaysFor: Player → Team (REL)
        """
        cmds = [
            # Node tables
            """CREATE NODE TABLE IF NOT EXISTS Team (
                id STRING PRIMARY KEY,
                name STRING,
                home_venue STRING,
                home_city STRING
            )""",
            """CREATE NODE TABLE IF NOT EXISTS Player (
                id STRING PRIMARY KEY,
                name STRING,
                team STRING,
                role STRING,
                is_foreign BOOLEAN,
                batting_style STRING,
                bowling_style STRING
            )""",
            """CREATE NODE TABLE IF NOT EXISTS Venue (
                id STRING PRIMARY KEY,
                name STRING,
                city STRING,
                capacity INT64,
                avg_first_innings_score INT64
            )""",
            # Relationship tables
            """CREATE REL TABLE IF NOT EXISTS PlaysFor (
                FROM Player TO Team
            )""",
            """CREATE REL TABLE IF NOT EXISTS PlayedAt (
                FROM Player TO Venue,
                innings INT64,
                runs INT64,
                avg DOUBLE,
                sr DOUBLE
            )""",
            """CREATE REL TABLE IF NOT EXISTS Matchup (
                FROM Player TO Player,
                balls INT64,
                runs INT64,
                wickets INT64,
                dots INT64
            )""",
        ]

        for cmd in cmds:
            try:
                self._conn.execute(cmd)
            except Exception as exc:
                # KuzuDB raises if table already exists in older versions
                if "already exists" in str(exc).lower():
                    logger.debug("Table already exists (skipping): %s", str(exc)[:100])
                else:
                    logger.error("Schema command failed: %s\nSQL: %s", exc, cmd[:120])
                    raise

        logger.info("KuzuDB schema ready (Team, Player, Venue, PlaysFor, PlayedAt, Matchup)")

    # ------------------------------------------------------------------
    # Query interface
    # ------------------------------------------------------------------

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Execute a Cypher query and return results as a list of dicts.

        Args:
            cypher: Cypher query string
            params: Optional query parameters (KuzuDB prepared statement style)

        Returns:
            List of row dicts. Empty list on error or no results.
        """
        try:
            if params:
                result = self._conn.execute(cypher, params)
            else:
                result = self._conn.execute(cypher)

            rows: list[dict[str, Any]] = []
            if result is not None:
                while result.has_next():
                    row = result.get_next()
                    col_names = result.get_column_names()
                    rows.append(dict(zip(col_names, row)))
            return rows

        except Exception as exc:
            logger.error("KuzuDB query failed: %s\nQuery: %s", exc, cypher[:200])
            return []

    def execute(self, cypher: str, params: dict[str, Any] | None = None) -> None:
        """
        Execute a write Cypher command (CREATE, MERGE, etc.).

        Args:
            cypher: Cypher command string
            params: Optional query parameters
        """
        try:
            if params:
                self._conn.execute(cypher, params)
            else:
                self._conn.execute(cypher)
        except Exception as exc:
            if "already exists" in str(exc).lower() or "violates unique" in str(exc).lower():
                logger.debug("Duplicate insert skipped: %s", str(exc)[:100])
            else:
                logger.error("KuzuDB execute failed: %s\nQuery: %s", exc, cypher[:200])
                raise

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def upsert_team(
        self,
        team_id: str,
        name: str,
        home_venue: str,
        home_city: str,
    ) -> None:
        """Insert or update a Team node."""
        try:
            self.execute(
                "CREATE (t:Team {id: $id, name: $name, home_venue: $hv, home_city: $hc})",
                {"id": team_id, "name": name, "hv": home_venue, "hc": home_city},
            )
        except Exception:
            pass  # already exists — KuzuDB has no MERGE yet; skip duplicate

    def upsert_player(
        self,
        player_id: str,
        name: str,
        team: str,
        role: str,
        is_foreign: bool,
        batting_style: str,
        bowling_style: str,
    ) -> None:
        """Insert or update a Player node."""
        try:
            self.execute(
                """CREATE (p:Player {
                    id: $id, name: $name, team: $team, role: $role,
                    is_foreign: $foreign, batting_style: $bs, bowling_style: $bws
                })""",
                {
                    "id": player_id, "name": name, "team": team, "role": role,
                    "foreign": is_foreign, "bs": batting_style, "bws": bowling_style,
                },
            )
        except Exception:
            pass

    def upsert_venue(
        self,
        venue_id: str,
        name: str,
        city: str,
        capacity: int,
        avg_first_innings_score: int,
    ) -> None:
        """Insert or update a Venue node."""
        try:
            self.execute(
                """CREATE (v:Venue {
                    id: $id, name: $name, city: $city,
                    capacity: $cap, avg_first_innings_score: $avg
                })""",
                {
                    "id": venue_id, "name": name, "city": city,
                    "cap": capacity, "avg": avg_first_innings_score,
                },
            )
        except Exception:
            pass

    def add_plays_for(self, player_id: str, team_id: str) -> None:
        """Add PlaysFor edge from Player to Team."""
        try:
            self.execute(
                """MATCH (p:Player {id: $pid}), (t:Team {id: $tid})
                   CREATE (p)-[:PlaysFor]->(t)""",
                {"pid": player_id, "tid": team_id},
            )
        except Exception:
            pass

    def add_played_at(
        self,
        player_id: str,
        venue_id: str,
        innings: int,
        runs: int,
        avg: float,
        sr: float,
    ) -> None:
        """Add or update PlayedAt edge from Player to Venue."""
        try:
            self.execute(
                """MATCH (p:Player {id: $pid}), (v:Venue {id: $vid})
                   CREATE (p)-[:PlayedAt {innings: $inn, runs: $runs, avg: $avg, sr: $sr}]->(v)""",
                {"pid": player_id, "vid": venue_id, "inn": innings, "runs": runs, "avg": avg, "sr": sr},
            )
        except Exception:
            pass

    def add_matchup(
        self,
        batter_id: str,
        bowler_id: str,
        balls: int,
        runs: int,
        wickets: int,
        dots: int,
    ) -> None:
        """Add Matchup edge from batter Player to bowler Player."""
        try:
            self.execute(
                """MATCH (b:Player {id: $bid}), (bw:Player {id: $bwid})
                   CREATE (b)-[:Matchup {balls: $balls, runs: $runs, wickets: $wkts, dots: $dots}]->(bw)""",
                {
                    "bid": batter_id, "bwid": bowler_id,
                    "balls": balls, "runs": runs, "wkts": wickets, "dots": dots,
                },
            )
        except Exception:
            pass

    def get_player_venue_stats(self, player_name: str, venue_name: str) -> dict[str, Any] | None:
        """
        Query PlayedAt edge for a player-venue combination.

        Returns dict with innings, runs, avg, sr or None if not found.
        """
        results = self.query(
            """MATCH (p:Player {name: $pname})-[r:PlayedAt]->(v:Venue {name: $vname})
               RETURN r.innings AS innings, r.runs AS runs, r.avg AS avg, r.sr AS sr""",
            {"pname": player_name, "vname": venue_name},
        )
        return results[0] if results else None

    def get_head_to_head(self, batter_name: str, bowler_name: str) -> dict[str, Any] | None:
        """
        Query Matchup edge for a batter-bowler pair.

        Returns dict with balls, runs, wickets, dots or None if not found.
        """
        results = self.query(
            """MATCH (b:Player {name: $bname})-[r:Matchup]->(bw:Player {name: $bwname})
               RETURN r.balls AS balls, r.runs AS runs, r.wickets AS wickets, r.dots AS dots""",
            {"bname": batter_name, "bwname": bowler_name},
        )
        return results[0] if results else None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the KuzuDB connection."""
        try:
            # KuzuDB connection cleanup
            del self._conn
            del self._db
            logger.info("KuzuDB connection closed")
        except Exception as exc:
            logger.warning("KuzuDB close warning: %s", exc)

    def __enter__(self) -> "KnowledgeGraph":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
