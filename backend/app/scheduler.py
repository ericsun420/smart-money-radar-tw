from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler


SCAN_JOB_ID = "scan_job"
DISCORD_QUEUE_JOB_ID = "discord_queue_job"
scheduler = BackgroundScheduler()


def configure_scan_job(scan_func, interval_minutes: int) -> None:
    scheduler.add_job(
        scan_func,
        "interval",
        minutes=interval_minutes,
        id=SCAN_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )


def reschedule_scan_job(interval_minutes: int, scan_func=None) -> None:
    job = scheduler.get_job(SCAN_JOB_ID)
    if job and scan_func:
        scheduler.remove_job(SCAN_JOB_ID)
        configure_scan_job(scan_func, interval_minutes)
    elif job:
        job.reschedule(trigger="interval", minutes=interval_minutes)


def configure_discord_queue_job(flush_func, interval_seconds: int = 30) -> None:
    scheduler.add_job(
        flush_func,
        "interval",
        seconds=interval_seconds,
        id=DISCORD_QUEUE_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )


def scheduler_status() -> dict:
    job = scheduler.get_job(SCAN_JOB_ID)
    return {
        "scheduler_running": scheduler.running,
        "next_run_time": job.next_run_time if job else None,
        "scan_interval_minutes": int(job.trigger.interval.total_seconds() // 60) if job and hasattr(job.trigger, "interval") else None,
        "discord_queue_next_run_time": scheduler.get_job(DISCORD_QUEUE_JOB_ID).next_run_time if scheduler.get_job(DISCORD_QUEUE_JOB_ID) else None,
    }
