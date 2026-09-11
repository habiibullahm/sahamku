"""Konfigurasi aplikasi: env vars + threshold sinyal."""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Asia/Jakarta")

DISCLAIMER = (
    "⚠️ Bukan saran investasi. Sinyal bersifat analitis berdasarkan data historis; "
    "keputusan transaksi sepenuhnya tanggung jawab Anda."
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = ""
    anthropic_api_key: str = ""
    admin_chat_id: int | None = None
    # Channel publik untuk broadcast laporan (mis. "@sahamku_id"); bot harus admin channel
    channel_id: str | None = None
    bot_username: str = "sahamku_id_bot"
    # Universe saham: lq45 | idx80
    universe: str = "lq45"
    # Kuota /ask per chat per hari (admin bebas kuota)
    ask_daily_limit: int = 10
    # Batas tier Free vs Pro (Pro diberikan admin: /admin pro <chat_id>)
    free_watchlist_max: int = 5
    free_alerts_max: int = 3
    pro_ask_daily_limit: int = 50
    pro_watchlist_max: int = 30
    pro_alerts_max: int = 20
    # Snapshot intraday (delayed) tiap N menit selama jam bursa
    intraday_interval_min: int = 15
    # Narasi AI 2-3 kalimat di laporan (dibuat sekali per hari per jenis laporan)
    narrative_enabled: bool = True
    db_path: Path = PROJECT_ROOT / "sahamku.db"
    charts_dir: Path = PROJECT_ROOT / "charts"

    # Override jadwal untuk testing (format "HH:MM"); kosong = jadwal default
    schedule_override_premarket: str | None = None
    schedule_override_aftermarket: str | None = None

    # Threshold sinyal (bisa dituning setelah backtest)
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    breakout_lookback: int = 20
    breakout_volume_mult: float = 1.5
    # Lebar Bollinger relatif ke mid dianggap squeeze jika < nilai ini
    bb_squeeze_pct: float = 0.06
    signal_bullish_threshold: int = 2
    signal_bearish_threshold: int = -2

    # LLM: "groq" (gratis) atau "anthropic"
    llm_provider: str = "groq"
    llm_model: str = "claude-opus-5"
    llm_max_tokens: int = 16000
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_max_tokens: int = 2048

    @field_validator("admin_chat_id", "channel_id", "schedule_override_premarket",
                     "schedule_override_aftermarket", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        return None if isinstance(v, str) and v.strip() == "" else v

    @property
    def db_path_abs(self) -> Path:
        p = self.db_path
        return p if p.is_absolute() else PROJECT_ROOT / p


settings = Settings()
