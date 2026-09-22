from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    playlist_id: str
    data_dir: Path
    podcasts_file: Path
    state_file: Path
    settings_file: Path

    @classmethod
    def load(cls) -> "AppConfig":
        load_dotenv(Path.cwd() / ".env")

        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)

        config = cls(
            client_id=os.getenv("SPOTIPY_CLIENT_ID", ""),
            client_secret=os.getenv("SPOTIPY_CLIENT_SECRET", ""),
            redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI", ""),
            playlist_id=os.getenv("PLAYLIST_ID", ""),
            data_dir=data_dir,
            podcasts_file=data_dir / "podcasts.json",
            state_file=data_dir / "state.json",
            settings_file=data_dir / "settings.json",
        )
        config.validate()
        return config

    def validate(self) -> None:
        missing = []
        if not self.client_id:
            missing.append("SPOTIPY_CLIENT_ID")
        if not self.client_secret:
            missing.append("SPOTIPY_CLIENT_SECRET")
        if not self.redirect_uri:
            missing.append("SPOTIPY_REDIRECT_URI")
        if not self.playlist_id:
            missing.append("PLAYLIST_ID")

        if missing:
            raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")
