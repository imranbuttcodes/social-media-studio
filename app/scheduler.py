"""
Scheduler module using APScheduler with SQLite job store.
The scheduler is started on import and lives for the lifetime of the
application process.  It persists jobs in a small SQLite file
(`scheduler.db`) so that scheduled publishes survive a process restart.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from datetime import datetime
import atexit

# Use a dedicated SQLite file for job persistence.
JOBSTORE_URL = "sqlite:///./scheduler.db"

jobstores = {
    "default": SQLAlchemyJobStore(url=JOBSTORE_URL)
}

scheduler = BackgroundScheduler(jobstores=jobstores, timezone="UTC")
# Start the scheduler immediately.
scheduler.start()   

# Graceful shutdown – ensure APScheduler shuts down cleanly when the process exits.
atexit.register(lambda: scheduler.shutdown(wait=False))

# Helper for debugging – expose the scheduler instance.
def get_scheduler() -> BackgroundScheduler:
    return scheduler
