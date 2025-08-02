# scripts/generate_report.py

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from app.database import SessionLocal, create_tables
from app import crud
from app.models import TradeInference, ActualTrade, TradeEvaluation

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ReportGenerator:
    """
    パフォーマンスレポートを生成し、Slackに通知するクラス
    """
    
    def __init__(self):
        self.slack_token = os.getenv("SLACK_BOT_TOKEN")
        self.report_channel_id = os.getenv("SLACK_REPORT_CHANNEL_ID", os.getenv("SLACK_CHANNEL_ID"))
        
        if self.slack_token and self.report_channel_id:
            self.slack_client = WebClient(token=self.slack_token)
        else:
            logger.warning("Slack credentials not found. Reports will only be logged.")
            self.slack_client = None
    
    def generate_report(self, period: str) -> Dict[str, Any]:
        """
        指定期間のパフォーマンスレポートを生成
        
        Args:
            period: 'daily', 'weekly', 'monthly', または 'all_time'
            
        Returns:
            レポートデータの辞書
        """
        logger.info(f"Generating {period} report")
        
        # 期間の計算
        end_date = datetime.utcnow()
        start_date = self._calculate_start_date(period, end_date)
        
        db = SessionLocal()
        try:
            # パフォーマンス統計を取得
            performance_summary = crud.get_performance_summary(db, start_date, end_date)
            
            # 詳細データを取得
            evaluations = crud.get_evaluations_in_period(db, start_date, end_date)
            
            # レポートデータを構築
            report_data = {
                'period': period,
                'start_date': start_date,
                'end_date': end_date,
                'performance': performance_summary,
                'inference_count': len(evaluations),
                'evaluation_details': self._analyze_evaluations(evaluations),
                'top_performers': self._get_top_performing_inferences(db, evaluations),
                'improvement_suggestions': self._generate_improvement_suggestions(performance_summary, evaluations)
            }
            
            # レポートをフォーマット
            formatted_report = self._format_report(report_data)
            
            # Slackに送信
            if self.slack_client:
                self._send_slack_report(formatted_report, period)
            
            logger.info(f"Report generation completed for period: {period}")
            return report_data
            
        finally:
            db.close()
    
    def _calculate_start_date(self, period: str, end_date: datetime) -> datetime:
        """
        期間に基づいて開始日を計算
        """
        if period == 'daily':
            return end_date - timedelta(days=1)
        elif period == 'weekly':
            return end_date - timedelta(days=7)
        elif period == 'monthly':
            return end_date - timedelta(days=30)
        elif period == 'all_time':
            return datetime(2020, 1, 1)  # 十分に過去の日付
        else:
            raise ValueError(f"Invalid period: {period}")
    
    def _analyze_evaluations(self, evaluations) -> Dict[str, Any]:
        """
        評価データを分析
        """
        if not evaluations:
            return {
                'average_logic_score': 0,
                'score_distribution': {},
                'average_potential_pnl': 0,
                'evaluation_completion_rate': 0
            }
        
        # ロジックスコアの分析
        logic_scores = [e.logic_evaluation_score for e in evaluations if e.logic_evaluation_score is not None]
        
        if logic_scores:
            avg_logic_score = sum(logic_scores) / len(logic_scores)
            score_distribution = {
                'score_5': len([s for s in logic_scores if s == 5]),
                'score_4': len([s for s in logic_scores if s == 4]),
                'score_3': len([s for s in logic_scores if s == 3]),
                'score_2': len([s for s in logic_scores if s == 2]),
                'score_1': len([s for s in logic_scores if s == 1])
            }
        else:
            avg_logic_score = 0
            score_distribution = {}
        
        # ポテンシャル損益の分析
        potential_pnls = [e.potential_profit_loss for e in evaluations if e.potential_profit_loss is not None]
        avg_potential_pnl = sum(potential_pnls) / len(potential_pnls) if potential_pnls else 0
        
        return {
            'average_logic_score': round(avg_logic_score, 2),
            'score_distribution': score_distribution,
            'average_potential_pnl': round(avg_potential_pnl, 2),
            'evaluation_completion_rate': len(logic_scores) / len(evaluations) * 100 if evaluations else 0
        }
    
    def _get_top_performing_inferences(self, db: Session, evaluations, limit: int = 3):
        """
        トップパフォーマンスの推論を取得
        """
        # ロジックスコアとポテンシャル損益でソート
        scored_evaluations = [
            e for e in evaluations 
            if e.logic_evaluation_score is not None and e.potential_profit_loss is not None
        ]
        
        if not scored_evaluations:
            return []
        
        # 複合スコアで並び替え（ロジックスコア * 0.6 + 正規化されたPnL * 0.4）
        def composite_score(evaluation):
            logic_weight = 0.6
            pnl_weight = 0.4
            
            # ロジックスコアを0-1に正規化
            normalized_logic = (evaluation.logic_evaluation_score - 1) / 4
            
            # PnLを正規化（簡易版）
            max_pnl = max([e.potential_profit_loss for e in scored_evaluations])
            min_pnl = min([e.potential_profit_loss for e in scored_evaluations])
            
            if max_pnl != min_pnl:
                normalized_pnl = (evaluation.potential_profit_loss - min_pnl) / (max_pnl - min_pnl)
            else:
                normalized_pnl = 0.5
            
            return logic_weight * normalized_logic + pnl_weight * normalized_pnl
        
        top_evaluations = sorted(scored_evaluations, key=composite_score, reverse=True)[:limit]
        
        return [
            {
                'inference_id': e.inference_id,
                'logic_score': e.logic_evaluation_score,
                'potential_pnl': e.potential_profit_loss,
                'summary': e.evaluation_summary[:100] + "..." if len(e.evaluation_summary) > 100 else e.evaluation_summary
            }
            for e in top_evaluations
        ]
    
    def _generate_improvement_suggestions(self, performance, evaluations) -> list:
        """
        改善提案を生成
        """
        suggestions = []
        
        # 勝率が低い場合
        if performance.get('win_rate', 0) < 50:
            suggestions.append("勝率向上のため、エントリータイミングの精度向上を検討してください")
        
        # 平均ロジックスコアが低い場合
        evaluation_details = self._analyze_evaluations(evaluations)
        if evaluation_details.get('average_logic_score', 0) < 3:
            suggestions.append("推論の質向上のため、より詳細な市場分析を含めることを推奨します")
        
        # プロフィットファクターが低い場合
        if performance.get('profit_factor', 0) < 1.2:
            suggestions.append("リスク管理の改善により、損失の制限と利益の最大化を図ってください")
        
        # 評価完了率が低い場合
        if evaluation_details.get('evaluation_completion_rate', 0) < 80:
            suggestions.append("推論の評価完了率向上のため、定期的な評価プロセスの実行を確認してください")
        
        return suggestions if suggestions else ["現在のパフォーマンスは良好です。継続的な改善を心がけてください。"]
    
    def _format_report(self, report_data: Dict[str, Any]) -> str:
        """
        レポートデータを読みやすい形式にフォーマット
        """
        period = report_data['period']
        perf = report_data['performance']
        eval_details = report_data['evaluation_details']
        
        # ヘッダー
        report = f"📊 **{period.upper()} 取引パフォーマンスレポート**\n"
        report += f"期間: {report_data['start_date'].strftime('%Y-%m-%d')} ～ {report_data['end_date'].strftime('%Y-%m-%d')}\n\n"
        
        # パフォーマンス統計
        report += "**📈 取引パフォーマンス**\n"
        report += f"• 総取引数: {perf['total_trades']}件\n"
        report += f"• 勝ち取引: {perf['winning_trades']}件\n"
        report += f"• 負け取引: {perf['losing_trades']}件\n"
        report += f"• 勝率: {perf['win_rate']:.1f}%\n"
        report += f"• 総損益: {perf['total_profit_loss']:.2f}\n"
        report += f"• 平均利益: {perf['average_profit']:.2f}\n"
        report += f"• 平均損失: {perf['average_loss']:.2f}\n"
        report += f"• プロフィットファクター: {perf['profit_factor']:.2f}\n\n"
        
        # 推論評価統計
        report += "**🧠 推論評価統計**\n"
        report += f"• 推論数: {report_data['inference_count']}件\n"
        report += f"• 平均ロジックスコア: {eval_details['average_logic_score']}/5.0\n"
        report += f"• 平均ポテンシャル損益: {eval_details['average_potential_pnl']:.2f}\n"
        report += f"• 評価完了率: {eval_details['evaluation_completion_rate']:.1f}%\n\n"
        
        # トップパフォーマンス
        if report_data['top_performers']:
            report += "**🏆 トップパフォーマンス推論**\n"
            for i, top in enumerate(report_data['top_performers'], 1):
                report += f"{i}. ID{top['inference_id']}: スコア{top['logic_score']}, PnL{top['potential_pnl']:.2f}\n"
            report += "\n"
        
        # 改善提案
        report += "**💡 改善提案**\n"
        for suggestion in report_data['improvement_suggestions']:
            report += f"• {suggestion}\n"
        
        report += f"\n_レポート生成時刻: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC_"
        
        return report
    
    def _send_slack_report(self, formatted_report: str, period: str):
        """
        フォーマットされたレポートをSlackに送信
        """
        try:
            # メッセージを送信
            response = self.slack_client.chat_postMessage(
                channel=self.report_channel_id,
                text=formatted_report,
                username="Forex Evaluation Bot",
                icon_emoji=":chart_with_upwards_trend:"
            )
            
            if response["ok"]:
                logger.info(f"Successfully sent {period} report to Slack")
            else:
                logger.error(f"Failed to send report to Slack: {response.get('error')}")
                
        except SlackApiError as e:
            logger.error(f"Slack API error when sending report: {e.response['error']}")
        except Exception as e:
            logger.error(f"Unexpected error when sending report: {e}")

def main():
    """
    メイン実行関数
    """
    parser = argparse.ArgumentParser(description="Generate and send performance reports")
    parser.add_argument(
        '--period',
        choices=['daily', 'weekly', 'monthly', 'all_time'],
        required=True,
        help='Report period'
    )
    
    args = parser.parse_args()
    
    try:
        # データベーステーブルが存在することを確認
        create_tables()
        
        # レポートジェネレーターを初期化
        generator = ReportGenerator()
        
        # レポートを生成・送信
        report_data = generator.generate_report(args.period)
        
        logger.info(f"Report generation completed for period: {args.period}")
        
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
