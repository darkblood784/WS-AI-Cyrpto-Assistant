from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET: str = "CHANGE_ME"
    JWT_ACCESS_MINUTES: int = 15
    JWT_REFRESH_DAYS: int = 30

settings = Settings()
