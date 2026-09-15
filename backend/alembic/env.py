import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings
from app.db.session import Base
from app.models import models  # noqa
target_metadata = Base.metadata
