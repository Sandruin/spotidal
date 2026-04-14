import datetime
import sqlalchemy
from sqlalchemy import Table, Column, String, DateTime, MetaData, insert, select, update, delete


class MatchFailureDatabase:
    """
    SQLite database of match failures which persists between runs.
    This can be used concurrently between multiple processes.
    """

    def __init__(self, filename='.cache.db'):
        self.engine = sqlalchemy.create_engine(f"sqlite:///{filename}")
        meta = MetaData()
        self.match_failures = Table('match_failures', meta,
                                    Column('track_id', String,
                                           primary_key=True),
                                    Column('insert_time', DateTime),
                                    Column('next_retry', DateTime),
                                    sqlite_autoincrement=False)
        meta.create_all(self.engine)

    def _get_next_retry_time(self, insert_time: datetime.datetime | None = None) -> datetime.datetime:
        if insert_time:
            # double interval on each retry
            interval = 2 * (datetime.datetime.now() - insert_time)
        else:
            interval = datetime.timedelta(days=7)
        return datetime.datetime.now() + interval

    def cache_match_failure(self, track_id: str):
        """Notifies that matching failed for the given track_id."""
        fetch_statement = select(self.match_failures).where(
            self.match_failures.c.track_id == track_id)
        with self.engine.connect() as connection:
            with connection.begin():
                existing_failure = connection.execute(
                    fetch_statement).fetchone()
                if existing_failure:
                    update_statement = update(self.match_failures).where(
                        self.match_failures.c.track_id == track_id).values(next_retry=self._get_next_retry_time())
                    connection.execute(update_statement)
                else:
                    connection.execute(insert(self.match_failures), {
                                       "track_id": track_id, "insert_time": datetime.datetime.now(), "next_retry": self._get_next_retry_time()})

    def has_match_failure(self, track_id: str) -> bool:
        """Checks if there was a recent search for which matching failed with the given track_id."""
        statement = select(self.match_failures.c.next_retry).where(
            self.match_failures.c.track_id == track_id)
        with self.engine.connect() as connection:
            match_failure = connection.execute(statement).fetchone()
            if match_failure:
                return match_failure.next_retry > datetime.datetime.now()
            return False

    def remove_match_failure(self, track_id: str):
        """Removes match failure from the database."""
        statement = delete(self.match_failures).where(
            self.match_failures.c.track_id == track_id)
        with self.engine.connect() as connection:
            with connection.begin():
                connection.execute(statement)


class SyncSnapshotDatabase:
    """
    Persists the set of matched track pairs after each bidirectional sync run.
    Used to detect deletions: if a pair was in the previous snapshot but one side
    is now missing, the track was deleted from that side.
    """

    def __init__(self, filename='.cache.db'):
        self.engine = sqlalchemy.create_engine(f"sqlite:///{filename}")
        meta = MetaData()
        self.sync_snapshots = Table('sync_snapshots', meta,
                                    Column('playlist_key', String, primary_key=True),
                                    Column('provider_a_id', String, primary_key=True),
                                    Column('provider_b_id', String, primary_key=True),
                                    Column('last_seen', DateTime))
        meta.create_all(self.engine)

    def save_snapshot(self, playlist_key: str, pairs: list[tuple[str, str]]):
        """Replace all entries for this playlist with current matched pairs."""
        with self.engine.connect() as connection:
            with connection.begin():
                connection.execute(
                    delete(self.sync_snapshots).where(
                        self.sync_snapshots.c.playlist_key == playlist_key))
                if pairs:
                    connection.execute(
                        insert(self.sync_snapshots),
                        [{"playlist_key": playlist_key, "provider_a_id": a, "provider_b_id": b,
                          "last_seen": datetime.datetime.now()} for a, b in pairs])

    def get_snapshot(self, playlist_key: str) -> set[tuple[str, str]]:
        """Get previous snapshot as set of (provider_a_id, provider_b_id) pairs."""
        statement = select(
            self.sync_snapshots.c.provider_a_id,
            self.sync_snapshots.c.provider_b_id,
        ).where(self.sync_snapshots.c.playlist_key == playlist_key)
        with self.engine.connect() as connection:
            rows = connection.execute(statement).fetchall()
            return {(row.provider_a_id, row.provider_b_id) for row in rows}


class TrackMatchCache:
    """
    Non-persistent mapping of source track ids -> destination track ids.
    This should NOT be accessed concurrently from multiple processes.
    """

    def __init__(self):
        self.data: dict[str, str] = {}

    def get(self, track_id: str) -> str | None:
        return self.data.get(track_id, None)

    def insert(self, source_id: str, dest_id: str):
        self.data[source_id] = dest_id
