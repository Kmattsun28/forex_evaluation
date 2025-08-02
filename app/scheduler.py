# app/scheduler.py

import logging
import subprocess
import sys
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ForexEvaluationScheduler:
    """
    為替取引評価システムの定期実行タスクを管理するスケジューラー
    """
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        logger.info("Forex Evaluation Scheduler initialized")
    
    def start_scheduler(self):
        """
        全ての定期実行ジョブを開始
        """
        logger.info("Starting scheduled jobs...")
        
        # 1. Slackからの推論ログ収集（10分ごと）
        self.scheduler.add_job(
            id='collect_inferences',
            func=self._run_inference_collection,
            trigger=IntervalTrigger(minutes=10),
            max_instances=1,  # 同時実行を防ぐ
            coalesce=True,    # 遅延実行時に複数のジョブをまとめる
            name="Collect inferences from Slack"
        )
        logger.info("Scheduled: Inference collection every 10 minutes")
        
        # 2. 推論評価実行（1時間ごと）
        self.scheduler.add_job(
            id='run_evaluations',
            func=self._run_evaluations,
            trigger=IntervalTrigger(hours=1),
            max_instances=1,
            coalesce=True,
            name="Run inference evaluations"
        )
        logger.info("Scheduled: Evaluation run every hour")
        
        # 3. 日次レポート生成（毎日AM 7:00）
        self.scheduler.add_job(
            id='daily_report',
            func=self._generate_daily_report,
            trigger=CronTrigger(hour=7, minute=0),
            max_instances=1,
            coalesce=True,
            name="Generate daily report"
        )
        logger.info("Scheduled: Daily report at 7:00 AM")
        
        # 4. 週次レポート生成（毎週月曜日AM 7:30）
        self.scheduler.add_job(
            id='weekly_report',
            func=self._generate_weekly_report,
            trigger=CronTrigger(day_of_week='mon', hour=7, minute=30),
            max_instances=1,
            coalesce=True,
            name="Generate weekly report"
        )
        logger.info("Scheduled: Weekly report on Monday at 7:30 AM")
        
        # 5. 月次レポート生成（毎月1日AM 8:00）
        self.scheduler.add_job(
            id='monthly_report',
            func=self._generate_monthly_report,
            trigger=CronTrigger(day=1, hour=8, minute=0),
            max_instances=1,
            coalesce=True,
            name="Generate monthly report"
        )
        logger.info("Scheduled: Monthly report on 1st day at 8:00 AM")
        
        logger.info("All scheduled jobs started successfully")
    
    def _run_inference_collection(self):
        """
        Slackからの推論ログ収集を実行
        """
        logger.info("Starting scheduled inference collection...")
        try:
            result = subprocess.run([
                sys.executable, 
                "scripts/collect_inferences_from_slack.py"
            ], capture_output=True, text=True, timeout=300)  # 5分でタイムアウト
            
            if result.returncode == 0:
                logger.info("Inference collection completed successfully")
                if result.stdout:
                    logger.info(f"Collection output: {result.stdout.strip()}")
            else:
                logger.error(f"Inference collection failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.error("Inference collection timed out")
        except Exception as e:
            logger.error(f"Error running inference collection: {e}")
    
    def _run_evaluations(self):
        """
        推論評価を実行
        """
        logger.info("Starting scheduled evaluation run...")
        try:
            result = subprocess.run([
                sys.executable, 
                "scripts/run_evaluation.py",
                "--max-evaluations", "50"
            ], capture_output=True, text=True, timeout=600)  # 10分でタイムアウト
            
            if result.returncode == 0:
                logger.info("Evaluation run completed successfully")
                if result.stdout:
                    logger.info(f"Evaluation output: {result.stdout.strip()}")
            else:
                logger.error(f"Evaluation run failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.error("Evaluation run timed out")
        except Exception as e:
            logger.error(f"Error running evaluations: {e}")
    
    def _generate_daily_report(self):
        """
        日次レポートを生成
        """
        logger.info("Starting scheduled daily report generation...")
        try:
            result = subprocess.run([
                sys.executable,
                "scripts/generate_report.py",
                "--period", "daily"
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                logger.info("Daily report generation completed successfully")
            else:
                logger.error(f"Daily report generation failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.error("Daily report generation timed out")
        except Exception as e:
            logger.error(f"Error generating daily report: {e}")
    
    def _generate_weekly_report(self):
        """
        週次レポートを生成
        """
        logger.info("Starting scheduled weekly report generation...")
        try:
            result = subprocess.run([
                sys.executable,
                "scripts/generate_report.py",
                "--period", "weekly"
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                logger.info("Weekly report generation completed successfully")
            else:
                logger.error(f"Weekly report generation failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.error("Weekly report generation timed out")
        except Exception as e:
            logger.error(f"Error generating weekly report: {e}")
    
    def _generate_monthly_report(self):
        """
        月次レポートを生成
        """
        logger.info("Starting scheduled monthly report generation...")
        try:
            result = subprocess.run([
                sys.executable,
                "scripts/generate_report.py",
                "--period", "monthly"
            ], capture_output=True, text=True, timeout=600)
            
            if result.returncode == 0:
                logger.info("Monthly report generation completed successfully")
            else:
                logger.error(f"Monthly report generation failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.error("Monthly report generation timed out")
        except Exception as e:
            logger.error(f"Error generating monthly report: {e}")
    
    def stop_scheduler(self):
        """
        スケジューラーを停止
        """
        logger.info("Stopping scheduler...")
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")
    
    def get_job_status(self):
        """
        現在のジョブステータスを取得
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        return jobs

# グローバルスケジューラーインスタンス
_scheduler_instance = None

def get_scheduler():
    """
    シングルトンスケジューラーインスタンスを取得
    """
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = ForexEvaluationScheduler()
    return _scheduler_instance

def start_scheduler():
    """
    スケジューラーを開始（FastAPIアプリケーションから呼び出される）
    """
    scheduler = get_scheduler()
    scheduler.start_scheduler()
    return scheduler

def stop_scheduler():
    """
    スケジューラーを停止
    """
    global _scheduler_instance
    if _scheduler_instance:
        _scheduler_instance.stop_scheduler()
        _scheduler_instance = None
