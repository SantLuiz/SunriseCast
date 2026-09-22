from dataclasses import asdict
from uuid import uuid4

from spotipy.exceptions import SpotifyException

from app.domain.models import Episode
from app.domain.progress import observe, reset_after_restore, utc_now


class SyncService:
    def __init__(self, playlist_id, podcasts_repository, settings_repository, state_repository,
                 episode_service, playlist_service):
        self.playlist_id = playlist_id
        self.podcasts_repository = podcasts_repository
        self.settings_repository = settings_repository
        self.state_repository = state_repository
        self.episode_service = episode_service
        self.playlist_service = playlist_service
        self.gateway = playlist_service.spotify_gateway
        self.report = lambda message: None
        self.now = utc_now

    def _save(self, state):
        self.state_repository.save(state)

    def _read(self, progress=False):
        return self.playlist_service.snapshot(self.playlist_id, progress)

    def _processed(self, state, ids):
        state["processed_episode_ids"] = sorted(set(state["processed_episode_ids"]) | set(ids))

    def _history(self, state, ids):
        return [h for h in state["history"] if h["id"] in ids]

    def _confirm(self, state, mutation, current, episodes):
        present = set(current)
        rows = self._history(state, mutation.get("history_ids", []))
        by_uri = {e.uri: e for e in episodes}
        now = self.now()
        observations = state["progress"].setdefault(mutation["playlist_id"], {})
        if mutation["kind"] == "remove":
            for row in rows:
                if row["episode"]["uri"] not in present:
                    row.update(status="removed", removed_at=now.isoformat(), error=None)
                    self._processed(state, [row["episode"]["id"]])
                else:
                    row.update(status="removal_failed", error="Remoção não confirmada; será reavaliada na próxima sincronização.")
        elif mutation["kind"] == "add":
            for raw in mutation.get("episodes", []):
                if raw["uri"] in present:
                    self._processed(state, [raw["id"]])
            for row in rows:
                uri = row["episode"]["uri"]
                if uri in present:
                    episode = by_uri.get(uri, Episode(**row["episode"]))
                    row.update(status="restored", restored_at=now.isoformat(), error=None)
                    reset_after_restore(episode, observations, now)
                else:
                    row.update(status="restore_failed", error="Episódio não encontrado após adicionar; tente novamente.")
        state["pending_mutation"] = None
        self._save(state)

    def _recover(self, state, episodes, current):
        mutation = state.get("pending_mutation")
        if mutation:
            if mutation["playlist_id"] != self.playlist_id:
                raise RuntimeError("Há uma alteração pendente em outra playlist. Volte à playlist anterior para conferir o resultado.")
            self.report("Conferindo alteração interrompida com a playlist atual")
            # Never repeat a stale HTTP request. Presence confirms effects; remaining work is replanned.
            self._confirm(state, mutation, current, episodes)

    def _mutate(self, state, kind, current, *, uris=None, episodes=None, history_ids=None, move=None):
        self.gateway.check_cancelled()
        mutation = {"id": uuid4().hex, "playlist_id": self.playlist_id, "kind": kind,
                    "created_at": self.now().isoformat(), "before": list(current),
                    "uris": uris or [], "episodes": [asdict(e) for e in (episodes or [])],
                    "history_ids": history_ids or [], "move": move}
        state["pending_mutation"] = mutation
        self._save(state)
        if kind == "remove":
            self.gateway.remove_all_occurrences_from_playlist(self.playlist_id, uris)
        elif kind == "add":
            self.gateway.add_items_to_playlist(self.playlist_id, uris)
        else:
            start, before, length = move
            self.gateway.reorder_items(self.playlist_id, start, before, length)
            segment = current[start:start + length]
            del current[start:start + length]
            current[before:before] = segment
            # Acknowledged reorder; if interrupted before this save, the next read replans it.
            state["pending_mutation"] = None
            self._save(state)
            return [], current
        confirmed, fresh = self._read()
        self._confirm(state, mutation, fresh, confirmed)
        return confirmed, fresh

    def _order(self, state, desired, current):
        # Preserve unrecognized entries and repeated occurrences; move contiguous blocks.
        wanted = [e.uri for e in desired]
        remaining = list(current)
        target = []
        for uri in wanted:
            while uri in remaining:
                remaining.remove(uri)
                target.append(uri)
        target.extend(remaining)
        moves = 0
        for index, uri in enumerate(target):
            if current[index] == uri:
                continue
            start = current.index(uri, index + 1)
            length = 1
            while start + length < len(current) and index + length < len(target) and current[start + length] == target[index + length]:
                length += 1
            self.report(f"Organizando por podcast: {index} de {len(target)} posições conferidas")
            _, current = self._mutate(state, "move", current, move=[start, index, length])
            moves += 1
        if moves:
            _, verified = self._read()
            if verified != target:
                raise RuntimeError("A playlist mudou durante a organização. Sincronize novamente para conferir a ordem.")
        return current

    def run_sync(self):
        self.playlist_service.report = self.report
        state = self.state_repository.load()
        settings = self.settings_repository.load()
        podcasts = self.podcasts_repository.load()
        self.report("Lendo playlist e progresso")
        episodes, current = self._read(progress=True)
        self._recover(state, episodes, current)
        observations = state["progress"].setdefault(self.playlist_id, {})
        removed_rows = []
        seen = set()
        for episode in episodes:
            if episode.id in seen:
                continue
            seen.add(episode.id)
            reason = observe(episode, observations, self.now())
            if reason:
                row = {"id": uuid4().hex, "playlist_id": self.playlist_id,
                       "episode": asdict(episode), "reason": reason, "status": "removal_pending",
                       "requested_at": self.now().isoformat(), "removed_at": None,
                       "restored_at": None, "error": None}
                removed_rows.append(row)
        self._save(state)
        for offset in range(0, len(removed_rows), 100):
            batch = removed_rows[offset:offset + 100]
            state["history"].extend(batch)
            self.report(f"Removendo episódios: lote de {len(batch)}")
            _, current = self._mutate(state, "remove", current,
                                      uris=[h["episode"]["uri"] for h in batch],
                                      history_ids=[h["id"] for h in batch])
        existing = [e for e in episodes if e.uri in current]
        processed = set(state["processed_episode_ids"])
        active = {e.id for e in existing}
        new = []
        for index, podcast in enumerate(podcasts, 1):
            self.report(f"Buscando novidades: {podcast.name} ({index}/{len(podcasts)})")
            for episode in self.episode_service.get_recent_unfinished_episodes(podcast, settings.interval_days):
                if episode.id not in processed and episode.id not in active:
                    active.add(episode.id)
                    new.append(episode)
        for offset in range(0, len(new), 100):
            batch = new[offset:offset + 100]
            self.report(f"Adicionando novidades: lote de {len(batch)}")
            _, current = self._mutate(state, "add", current, uris=[e.uri for e in batch], episodes=batch)
            if any(e.uri not in current for e in batch):
                raise RuntimeError("Algumas novidades não foram confirmadas na playlist. Tente novamente.")
        desired = self.playlist_service.build_desired_order(existing, new, podcasts)
        current = self._order(state, desired, current)
        self._processed(state, [e.id for e in desired])
        confirmed = [h for h in removed_rows if h["status"] == "removed"]
        if len(confirmed) != len(removed_rows):
            self._save(state)
            raise RuntimeError("Algumas remoções não foram confirmadas. Consulte o histórico e sincronize novamente.")
        state.update(last_sync_at=self.now().isoformat(), last_removed_count=len(confirmed),
                     last_playlist_size=len(current))
        self._save(state)
        return {"success": True, "kind": "sync", "removed_finished": sum(h["reason"] == "finished" for h in confirmed),
                "removed_stalled": sum(h["reason"] == "stalled" for h in confirmed),
                "new_found": len(new), "final_total": len(current), "interval_days": settings.interval_days}

    def run_restore(self, history_ids):
        self.playlist_service.report = self.report
        state = self.state_repository.load()
        episodes, current = self._read()
        self._recover(state, episodes, current)
        rows = [h for h in self._history(state, history_ids) if h["playlist_id"] == self.playlist_id
                and h.get("removed_at") and h["status"] != "restored"]
        missing = []
        for row in rows:
            episode = Episode(**row["episode"])
            if episode.uri in current:
                actual = next((e for e in episodes if e.uri == episode.uri), episode)
                reset_after_restore(actual, state["progress"].setdefault(self.playlist_id, {}), self.now())
                row.update(status="restored", restored_at=self.now().isoformat(), error=None)
                self._processed(state, [episode.id])
                self._save(state)
                continue
            missing.append(row)
        for offset in range(0, len(missing), 100):
            batch = missing[offset:offset + 100]
            self.report(f"Restaurando episódios: lote de {len(batch)}")
            try:
                episodes, current = self._restore_batch(state, batch, current)
            except SpotifyException as exc:
                if exc.http_status not in (400, 403, 404):
                    raise
                # Reconcile even a rejected batch before isolating individual failures.
                episodes, current = self._read()
                self._recover(state, episodes, current)
                for row in batch:
                    if row["status"] == "restored":
                        continue
                    try:
                        episodes, current = self._restore_batch(state, [row], current)
                    except SpotifyException as item_error:
                        if item_error.http_status not in (400, 403, 404):
                            raise
                        episodes, current = self._read()
                        self._recover(state, episodes, current)
                        if row["status"] != "restored":
                            row.update(status="restore_failed", error=f"Spotify recusou o episódio (HTTP {item_error.http_status}).")
                            self._save(state)
        # Include all currently present episodes, including additions and existing duplicates.
        episodes, current = self._read()
        desired = self.playlist_service.build_desired_order(episodes, [], self.podcasts_repository.load())
        self._order(state, desired, current)
        selected = self._history(state, history_ids)
        results = [{"id": h["id"], "name": h["episode"]["name"], "status": h["status"],
                    "error": h.get("error")} for h in selected]
        restored = sum(h["status"] == "restored" for h in selected)
        return {"success": restored == len(selected), "kind": "restore", "restored": restored,
                "failed": len(selected) - restored, "results": results, "final_total": len(current)}

    def _restore_batch(self, state, rows, current):
        unique = {}
        for row in rows:
            row.update(status="restore_pending", error=None)
            episode = Episode(**row["episode"])
            unique[episode.uri] = episode
        return self._mutate(state, "add", current, uris=list(unique), episodes=list(unique.values()),
                            history_ids=[row["id"] for row in rows])
