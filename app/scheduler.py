# app/scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import subprocess
import sys
import os

def run_script(script_path, *args):
    """指定されたスクリプトをpythonで実行する関数"""
    try:
        # appディレクトリをPythonパスに追加
        env = os.environ.copy()
        env['PYTHONPATH'] = f"{env.get('PYTHONPATH', '')}:/app"
        
        command = [sys.executable, script_path] + list(args)
        print(f"Running command: {' '.join(command)}")
        
        result = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            check=True,
            env=env
        )
        print(f"Successfully ran {script_path}:\n{result.stdout}")
    except subprocess.CalledProcessError as e:
        print(f"Error running script {script_path}: {e}\n{e.stderr}")
    except Exception as e:
        print(f"An unexpected error occurred while running {script_path}: {e}")

def start_scheduler():
    scheduler = BackgroundScheduler(timezone='Asia/Tokyo')
    
    # 1. Slackからの推論ログ収集 (10分ごと)
    scheduler.add_job(
        run_script, 
        'interval', 
        minutes=10, 
        args=['scripts/collect_inferences_from_slack.py'],
        next_run_time=datetime.now()
    )
    
    # 2. 個別評価の実行 (1時間ごと)
    scheduler.add_job(
        run_script, 
        'interval', 
        hours=1, 
        args=['scripts/run_evaluation.py'],
        next_run_time=datetime.now()
    )
    
    # 3. 日次レポートの生成 (毎日 AM 7:00 JST)
    scheduler.add_job(
        run_script,
        'cron',
        hour=7,
        minute=0,
        args=['scripts/generate_report.py', '--period', 'daily']
    )
    
    # 4. 週次レポートの生成 (毎週月曜 AM 7:30 JST)
    scheduler.add_job(
        run_script,
        'cron',
        day_of_week='mon',
        hour=7,
        minute=30,
        args=['scripts/generate_report.py', '--period', 'weekly']
    )
    
    print("Scheduler started with the following jobs:")
    for job in scheduler.get_jobs():
        print(f"- {job.name}: trigger={job.trigger}")
        
    scheduler.start()

class ForexEvaluationScheduler:
    """
    簡易版スケジューラー（下位互換性のため保持）
    """
    def __init__(self):
        self.scheduler = None
    
    def start_scheduler(self):
        """既存のstart_scheduler関数を呼び出す"""
        start_scheduler()
    
    def stop_scheduler(self):
        """スケジューラーを停止"""
        if self.scheduler:
            self.scheduler.shutdown()

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

def stop_scheduler():
    """
    スケジューラーを停止
    """
    global _scheduler_instance
    if _scheduler_instance:
        _scheduler_instance.stop_scheduler()
        _scheduler_instance = None
