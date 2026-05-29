import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    bot_token: str
    db_path: str
    reference_xlsx: str
    export_xlsx: str
    admins: set[int]

def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is empty")

    admins_raw = os.getenv("ADMINS", "").strip()
    admins = set()
    if admins_raw:
        admins = {int(x.strip()) for x in admins_raw.split(",") if x.strip().isdigit()}

    return Config(
        bot_token=token,
        db_path=os.getenv("DB_PATH", "inventory.sqlite3").strip(),
        reference_xlsx=os.getenv("REFERENCE_XLSX", "./data/os_reference.xlsx").strip(),
        export_xlsx=os.getenv("EXPORT_XLSX", "./data/os_result.xlsx").strip(),
        admins=admins,
    )