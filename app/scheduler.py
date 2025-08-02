# app/scheduler.py

import logging
import subprocess
import sys
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import os

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _run_script(script_path, *args):
    """指定されたスクリプトをpythonで実行する内部関数"""
    try:
        env = os.environ.copy()
        env['PYTHONPATH'] = f"{env.get('PYTHONPATH', '')}:/app"
        command = [sys.executable, script_path] + list(args)
        logger.info(f"Running command: {' '.join(command)}")
        result = subprocess.run(
            command, capture_output=True, text=True, check=True, env=env
        )
        logger.info(f"Successfully ran {script_path}:\n{result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running script {script_path}: {e}\n{e.stderr}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while running {script_path}: {e}")

class ForexEvaluationScheduler:
    """
    為替取引評価システムの定期実行タスクを管理するシングルトンクラス
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ForexEvaluationScheduler, cls).__new__(cls)
            cls._instance.scheduler = BackgroundScheduler(timezone='Asia/Tokyo')
            logger.info("Forex Evaluation Scheduler initialized")
        return cls._instance

    def start(self):
        """全ての定期実行ジョブを開始"""
        if self.scheduler.running:
            logger.info("Scheduler is already running.")
            return

        logger.info("Starting scheduled jobs...")
        # 1. Slackからの推論ログ収集（10分ごと）
        self.scheduler.add_job(
            id='collect_inferences', func=_run_script, trigger=IntervalTrigger(minutes=10),
            args=['scripts/collect_inferences_from_slack.py'], name="Collect inferences from Slack",
            max_instances=1, coalesce=True, next_run_time=datetime.now()
        )
        # 2. 推論評価実行（1時間ごと）
        self.scheduler.add_job(
            id='run_evaluations', func=_run_script, trigger=IntervalTrigger(hours=1),
            args=['scripts/run_evaluation.py', '--max-evaluations', '50'], name="Run inference evaluations",
            max_instances=1, coalesce=True, next_run_time=datetime.now()
        )
        # 3. 日次レポート生成（毎日AM 7:00）
        self.scheduler.add_job(
            id='daily_report', func=_run_script, trigger=CronTrigger(hour=7, minute=0),
            args=['scripts/generate_report.py', '--period', 'daily'], name="Generate daily report",
            max_instances=1, coalesce=True
        )
        # 4. 週次レポート生成（毎週月曜日AM 7:30）
        self.scheduler.add_job(
            id='weekly_report', func=_run_script, trigger=CronTrigger(day_of_week='mon', hour=7, minute=30),
            args=['scripts/generate_report.py', '--period', 'weekly'], name="Generate weekly report",
            max_instances=1, coalesce=True
        )
        # 5. 月次レポート生成（毎月1日AM 8:00）
        self.scheduler.add_job(
            id='monthly_report', func=_run_script, trigger=CronTrigger(day=1, hour=8, minute=0),
            args=['scripts/generate_report.py', '--period', 'monthly'], name="Generate monthly report",
            max_instances=1, coalesce=True
        )
        
        self.scheduler.start()
        logger.info("All scheduled jobs started successfully")

    def stop(self):
        """スケジューラーを停止"""
        if self.scheduler.running:
            logger.info("Stopping scheduler...")
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")

    def get_job_status(self):
        """現在のジョブステータスを取得"""
        if not self.scheduler.running:
            return {"status": "stopped", "jobs": []}
        
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id, 'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        return jobs

# --- FastAPIから呼び出される関数群 ---

_scheduler_instance = ForexEvaluationScheduler()

def get_scheduler():
    """シングルトンスケジューラーインスタンスを取得"""
    return _scheduler_instance

def start_scheduler():
    """スケジューラーを開始"""
    get_scheduler().start()

def stop_scheduler():
    """スケジューラーを停止"""
    get_scheduler().stop()