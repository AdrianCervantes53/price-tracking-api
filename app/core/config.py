from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    mongodb_url: str
    mongodb_db_name: str = "price_tracking"

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # MercadoLibre — kept for reference; source is deprecated (API returns 403)
    ml_site_id: str = "MLM"

    # Finnhub — kept for reference; not exposed in public API (ToS prohibits redistribution)
    finnhub_api_key: str = ""

    # CoinGecko Demo API — optional but recommended for a stable 30 req/min rate limit
    # Without a key the rate limit is dynamic (5–15 req/min depending on server load)
    # Get a free Demo key at coingecko.com/en/api
    coingecko_api_key: str | None = None


settings = Settings()
