from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./data/fantasy_dashboard.db"

    # Yahoo OAuth2
    yahoo_client_id: str = ""
    yahoo_client_secret: str = ""
    yahoo_redirect_uri: str = "http://localhost:8000/auth/yahoo/callback"

    # Scheduling
    lineup_check_start_hour: int = 14
    lineup_check_end_hour: int = 23
    lineup_check_interval_minutes: int = 10
    stats_sync_hour: int = 3
    timezone: str = "America/New_York"

    # External Data
    mlb_stats_api_base: str = "https://statsapi.mlb.com/api/v1"
    savant_base_url: str = "https://baseballsavant.mlb.com"
    fangraphs_base_url: str = "https://www.fangraphs.com"

    # Feature Flags
    enable_alerts: bool = True
    enable_prospect_tracking: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
