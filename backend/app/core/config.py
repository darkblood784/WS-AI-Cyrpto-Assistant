from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET: str
    JWT_ACCESS_MINUTES: int = 15
    JWT_REFRESH_DAYS: int = 30
    CORS_ALLOW_ORIGINS: str = "https://wsai.tw,https://www.wsai.tw,http://localhost:3010,http://127.0.0.1:3010"
    MAIL_FROM: str = "no-reply@wsai.tw"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    SMTP_TIMEOUT_SECS: int = 15
    VERIFY_LINK_BASE: str = "https://wsai.tw/verify-email"

settings = Settings()


def _validate_jwt_secret(secret: str) -> None:
    s = (secret or "").strip()
    if len(s) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 characters.")
    if s.lower() in {"change_me", "changeme", "default", "secret", "jwt_secret"}:
        raise RuntimeError("JWT_SECRET is using an insecure default value.")


_validate_jwt_secret(settings.JWT_SECRET)
