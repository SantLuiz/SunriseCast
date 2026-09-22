import json
import shutil
from pathlib import Path
from uuid import uuid4

from app.repositories.atomic import atomic_json
from app.domain.progress import parse_time, utc_now


class InvalidStateError(RuntimeError):
    pass


class StateRepository:
    VERSION = 2

    def __init__(self, file_path: Path, playlist_id: str | None = None):
        self.file_path = file_path
        self.playlist_id = playlist_id
        if not file_path.exists():
            self.save(self.empty())

    @staticmethod
    def empty():
        return {"version": 2, "processed_episode_ids": [], "last_sync_at": None,
                "progress": {}, "history": [], "pending_mutation": None,
                "pending_operation": None, "spotify_wait": None, "rate_limit_streak": 0}

    def load(self):
        try:
            state = json.loads(self.file_path.read_text(encoding="utf-8"))
            self.validate(state)
        except (ValueError, TypeError, KeyError) as exc:
            raise InvalidStateError(f"Estado inválido em {self.file_path}. Arquivo preservado; restaure um backup.") from exc
        if state.get("version", 1) == 1:
            backup = self.file_path.with_name(f"{self.file_path.name}.v1-{uuid4().hex[:8]}.bak")
            shutil.copy2(self.file_path, backup)
            state = {**self.empty(), **state, "version": self.VERSION}
            legacy_wait = self.file_path.with_name("legacy_spotify_wait.json")
            if self.playlist_id and legacy_wait.exists():
                try:
                    wait = json.loads(legacy_wait.read_text(encoding="utf-8-sig"))
                    until = parse_time(wait.get("until"))
                    if until and until > utc_now():
                        state["spotify_wait"] = wait
                        state["pending_operation"] = {"kind": "sync", "playlist_id": self.playlist_id, "auto_retry": True}
                except (ValueError, AttributeError) as exc:
                    raise InvalidStateError(f"Espera legada inválida em {legacy_wait}; arquivo preservado.") from exc
            self.save(state)
        return state

    @classmethod
    def validate(cls, state):
        if not isinstance(state, dict) or state.get("version", 1) not in (1, 2):
            raise ValueError("Versão de estado incompatível")
        ids = state.get("processed_episode_ids")
        if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids):
            raise ValueError("IDs inválidos")
        if state.get("version", 1) == 1:
            return
        if not isinstance(state["progress"], dict) or not isinstance(state["history"], list):
            raise ValueError("Histórico inválido")
        for episodes in state["progress"].values():
            if not isinstance(episodes, dict) or not all(isinstance(v, dict) for v in episodes.values()):
                raise ValueError("Progresso inválido")
            for progress in episodes.values():
                position = progress.get("position_ms")
                if position is not None and (type(position) is not int or position < 0):
                    raise ValueError("Posição inválida")
                if progress.get("last_advance_at") and not parse_time(progress["last_advance_at"]):
                    raise ValueError("Data de progresso inválida")
        for item in state["history"]:
            if not isinstance(item, dict) or not all(k in item for k in ("id", "playlist_id", "episode", "reason", "status")):
                raise ValueError("Remoção inválida")
            if not isinstance(item["episode"], dict) or not all(k in item["episode"] for k in ("id", "uri", "name", "show_id", "show_name", "release_date")):
                raise ValueError("Episódio inválido")
            if item["reason"] not in ("finished", "stalled") or item["status"] not in (
                    "removed", "restored", "removal_pending", "removal_failed", "restore_pending", "restore_failed"):
                raise ValueError("Situação de histórico inválida")
            for key in ("removed_at", "restored_at", "requested_at"):
                if item.get(key) is not None and not parse_time(item[key]):
                    raise ValueError("Data de histórico inválida")
        for key in ("spotify_wait", "pending_operation", "pending_mutation"):
            if state.get(key) is not None and not isinstance(state[key], dict):
                raise ValueError("Operação inválida")
        wait = state.get("spotify_wait")
        if wait is not None and (not parse_time(wait.get("until")) or not isinstance(wait.get("reason"), str)):
            raise ValueError("Espera inválida")
        operation = state.get("pending_operation")
        if operation is not None:
            if operation.get("kind") not in ("sync", "restore") or not operation.get("playlist_id"):
                raise ValueError("Operação pendente inválida")
            if operation["kind"] == "restore" and not isinstance(operation.get("history_ids"), list):
                raise ValueError("Seleção de restauração inválida")
        mutation = state.get("pending_mutation")
        if mutation is not None and (mutation.get("kind") not in ("remove", "add", "move")
                                     or not mutation.get("playlist_id") or not isinstance(mutation.get("before"), list)):
            raise ValueError("Alteração pendente inválida")
        if type(state.get("rate_limit_streak")) is not int or state["rate_limit_streak"] < 0:
            raise ValueError("Contador de espera inválido")

    def save(self, state):
        self.validate(state)
        atomic_json(self.file_path, state)
