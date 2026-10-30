import os
import sys

if sys.platform == "win32":
    # Some Windows machines (Smart App Control) block SQLAlchemy's compiled extensions. The pure-Python
    # implementation behaves identically; Linux containers keep the speed-ups.
    os.environ.setdefault("DISABLE_SQLALCHEMY_CEXT_RUNTIME", "1")
