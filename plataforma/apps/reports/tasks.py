from config.celery import app
from apps.reports.services import DailyFleetReportService


@app.task(name="apps.reports.tasks.check_daily_fleet_report_schedule")
def check_daily_fleet_report_schedule() -> dict[str, object]:
    return DailyFleetReportService().check_schedule()


@app.task(name="apps.reports.tasks.send_daily_fleet_report")
def send_daily_fleet_report(report_date: str | None = None) -> dict[str, object]:
    return DailyFleetReportService().send_for_date(report_date, mark_sent=True)
