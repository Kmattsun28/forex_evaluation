#!/usr/bin/env python3
"""
資産状況・評価損益計算スクリプト
取引ログと最新為替レートから、手数料を考慮した現在の保有資産と評価損益を計算し、Slackに通知する。
"""

import json
import os
import logging
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Dict, Optional

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 設定
SPREAD_CONFIG = {
    "USDJPY": 0.15,
    "EURJPY": 0.15, 
    "EURUSD": 0.0018
}

def get_rate_from_google(pair: str) -> Optional[float]:
    """Google Financeから為替レートを取得"""
    try:
        url = f"https://www.google.com/finance/quote/{pair[:3]}-{pair[3:6]}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # Google Financeの価格要素を検索
        price_element = soup.find('div', {'data-last-price': True})
        if price_element:
            rate = float(price_element['data-last-price'])
            logger.info(f"Google Finance rate for {pair}: {rate}")
            return rate
        
        # 別のセレクターを試行
        price_elements = soup.find_all('div', class_='YMlKec fxKbKc')
        if price_elements:
            rate = float(price_elements[0].text.replace(',', ''))
            logger.info(f"Google Finance rate for {pair}: {rate}")
            return rate
            
        logger.warning(f"Could not find price element for {pair} on Google Finance")
        return None
        
    except Exception as e:
        logger.error(f"Error fetching rate from Google Finance for {pair}: {e}")
        return None

def get_rate_from_yfinance(pair: str) -> Optional[float]:
    """yfinanceから為替レートを取得"""
    try:
        # yfinanceの通貨ペア形式に変換 (例: USDJPY -> USDJPY=X)
        yf_symbol = f"{pair}=X"
        ticker = yf.Ticker(yf_symbol)
        data = ticker.history(period="1d", interval="1m")
        
        if data.empty:
            logger.warning(f"No data returned from yfinance for {yf_symbol}")
            return None
            
        latest_rate = data['Close'].iloc[-1]
        logger.info(f"yfinance rate for {pair}: {latest_rate}")
        return float(latest_rate)
        
    except Exception as e:
        logger.error(f"Error fetching rate from yfinance for {pair}: {e}")
        return None

def get_latest_fx_rate(pair: str) -> Optional[float]:
    """最新の為替レートを取得（Google Finance優先、失敗時はyfinanceにフォールバック）"""
    logger.info(f"Fetching latest rate for {pair}")
    
    # Google Financeを試行
    rate = get_rate_from_google(pair)
    if rate is not None:
        return rate
    
    # yfinanceにフォールバック
    logger.info(f"Falling back to yfinance for {pair}")
    rate = get_rate_from_yfinance(pair)
    if rate is not None:
        return rate
    
    logger.error(f"Failed to fetch rate for {pair} from all sources")
    return None

def load_transaction_log() -> list:
    """取引ログを読み込み"""
    log_path = "/app/deal_log/transaction_log.json"
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('transactions', [])
    except FileNotFoundError:
        logger.error(f"Transaction log not found at {log_path}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing transaction log: {e}")
        return []
    except Exception as e:
        logger.error(f"Error loading transaction log: {e}")
        return []

def calculate_holdings_and_pnl() -> Dict:
    """保有資産と評価損益を計算"""
    # 初期化
    holdings = {'JPY': 100000.0, 'USD': 0.0, 'EUR': 0.0}
    costs = {'USD': 0.0, 'EUR': 0.0}
    realized_pnl = {'USD': 0.0, 'EUR': 0.0}
    
    # 取引ログを読み込み
    transactions = load_transaction_log()
    logger.info(f"Processing {len(transactions)} transactions")
    
    # 取引を時系列で処理
    for t in transactions:
        try:
            pair = t['currency_pair']
            amount = t['amount']
            rate = t['rate']
            spread = SPREAD_CONFIG.get(pair, 0)
            
            if amount > 0:  # 買い取引
                cost_per_unit = rate + spread
                total_cost_jpy = amount * cost_per_unit
                
                holdings['JPY'] -= total_cost_jpy
                holdings[pair[:3]] += amount
                costs[pair[:3]] += total_cost_jpy
                
                logger.debug(f"Buy: {amount} {pair[:3]} at {cost_per_unit} JPY/unit")
                
            else:  # 売り取引
                amount_to_sell = abs(amount)
                avg_buy_rate = costs[pair[:3]] / holdings[pair[:3]] if holdings[pair[:3]] > 0 else 0
                cost_of_sold_asset = amount_to_sell * avg_buy_rate
                proceeds_jpy = amount_to_sell * (rate - spread)
                pnl = proceeds_jpy - cost_of_sold_asset
                
                realized_pnl[pair[:3]] += pnl
                holdings['JPY'] += proceeds_jpy
                holdings[pair[:3]] -= amount_to_sell
                costs[pair[:3]] -= cost_of_sold_asset
                
                logger.debug(f"Sell: {amount_to_sell} {pair[:3]} at {rate - spread} JPY/unit, PnL: {pnl}")
                
        except Exception as e:
            logger.error(f"Error processing transaction {t}: {e}")
            continue
    
    # 最新レート取得
    current_rates = {
        'USDJPY': get_latest_fx_rate("USDJPY"),
        'EURJPY': get_latest_fx_rate("EURJPY")
    }
    
    # 評価損益計算
    result = {
        'timestamp': datetime.now().isoformat(),
        'holdings': holdings,
        'costs': costs,
        'realized_pnl': realized_pnl,
        'current_rates': current_rates,
        'unrealized_pnl': {},
        'pnl_per_unit': {},
        'current_values': {},
        'total_assets_jpy': 0.0
    }
    
    # USD評価損益
    if holdings['USD'] > 0 and current_rates['USDJPY'] is not None:
        avg_rate_usd = costs['USD'] / holdings['USD']
        current_value_usd_jpy = holdings['USD'] * current_rates['USDJPY']
        unrealized_pnl_usd = current_value_usd_jpy - costs['USD']
        pnl_per_usd = current_rates['USDJPY'] - avg_rate_usd
        
        result['unrealized_pnl']['USD'] = unrealized_pnl_usd
        result['pnl_per_unit']['USD'] = pnl_per_usd
        result['current_values']['USD'] = current_value_usd_jpy
        result['avg_rates'] = {'USD': avg_rate_usd}
    else:
        result['unrealized_pnl']['USD'] = 0.0
        result['pnl_per_unit']['USD'] = 0.0
        result['current_values']['USD'] = 0.0
        result['avg_rates'] = {'USD': 0.0}
    
    # EUR評価損益
    if holdings['EUR'] > 0 and current_rates['EURJPY'] is not None:
        avg_rate_eur = costs['EUR'] / holdings['EUR']
        current_value_eur_jpy = holdings['EUR'] * current_rates['EURJPY']
        unrealized_pnl_eur = current_value_eur_jpy - costs['EUR']
        pnl_per_eur = current_rates['EURJPY'] - avg_rate_eur
        
        result['unrealized_pnl']['EUR'] = unrealized_pnl_eur
        result['pnl_per_unit']['EUR'] = pnl_per_eur
        result['current_values']['EUR'] = current_value_eur_jpy
        result['avg_rates']['EUR'] = avg_rate_eur
    else:
        result['unrealized_pnl']['EUR'] = 0.0
        result['pnl_per_unit']['EUR'] = 0.0
        result['current_values']['EUR'] = 0.0
        result['avg_rates']['EUR'] = 0.0
    
    # 総資産計算
    result['total_assets_jpy'] = (
        holdings['JPY'] + 
        result['current_values']['USD'] + 
        result['current_values']['EUR']
    )
    
    return result

def format_report(data: Dict) -> str:
    """レポートを見やすい形式に整形"""
    report = "📊 **為替取引 資産状況・評価損益レポート**\n"
    report += f"🕒 更新時刻: {data['timestamp'][:19].replace('T', ' ')}\n\n"
    
    # 現在の保有残高
    report += "💰 **現在の保有残高**\n"
    report += f"・JPY: {data['holdings']['JPY']:,.0f} 円\n"
    report += f"・USD: {data['holdings']['USD']:,.2f} ドル\n"
    report += f"・EUR: {data['holdings']['EUR']:,.2f} ユーロ\n\n"
    
    # 最新レート
    report += "📈 **最新為替レート**\n"
    if data['current_rates']['USDJPY']:
        report += f"・USD/JPY: {data['current_rates']['USDJPY']:.2f}\n"
    if data['current_rates']['EURJPY']:
        report += f"・EUR/JPY: {data['current_rates']['EURJPY']:.2f}\n"
    report += "\n"
    
    # USD評価損益
    if data['holdings']['USD'] > 0:
        report += "💵 **USD ポジション**\n"
        report += f"・保有量: {data['holdings']['USD']:,.2f} USD\n"
        report += f"・平均取得レート: {data['avg_rates']['USD']:.2f} JPY/USD\n"
        report += f"・現在価値: {data['current_values']['USD']:,.0f} 円\n"
        report += f"・評価損益: {data['unrealized_pnl']['USD']:+,.0f} 円\n"
        report += f"・1USD当たり損益: {data['pnl_per_unit']['USD']:+.2f} 円\n"
        report += f"・実現損益: {data['realized_pnl']['USD']:+,.0f} 円\n\n"
    
    # EUR評価損益
    if data['holdings']['EUR'] > 0:
        report += "💶 **EUR ポジション**\n"
        report += f"・保有量: {data['holdings']['EUR']:,.2f} EUR\n"
        report += f"・平均取得レート: {data['avg_rates']['EUR']:.2f} JPY/EUR\n"
        report += f"・現在価値: {data['current_values']['EUR']:,.0f} 円\n"
        report += f"・評価損益: {data['unrealized_pnl']['EUR']:+,.0f} 円\n"
        report += f"・1EUR当たり損益: {data['pnl_per_unit']['EUR']:+.2f} 円\n"
        report += f"・実現損益: {data['realized_pnl']['EUR']:+,.0f} 円\n\n"
    
    # 総資産・総合損益
    total_unrealized = data['unrealized_pnl']['USD'] + data['unrealized_pnl']['EUR']
    total_realized = data['realized_pnl']['USD'] + data['realized_pnl']['EUR']
    total_pnl = total_unrealized + total_realized
    
    report += "💎 **総合資産状況**\n"
    report += f"・総資産: {data['total_assets_jpy']:,.0f} 円\n"
    report += f"・総評価損益: {total_unrealized:+,.0f} 円\n"
    report += f"・総実現損益: {total_realized:+,.0f} 円\n"
    report += f"・総合損益: {total_pnl:+,.0f} 円\n"
    
    return report

def send_to_slack(message: str) -> bool:
    """Slackにメッセージを送信"""
    webhook_url = os.getenv('SLACK_HOLDINGS_WEBHOOK_URL')
    if not webhook_url:
        logger.error("SLACK_HOLDINGS_WEBHOOK_URL environment variable not set")
        return False
    
    try:
        payload = {'text': message}
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Successfully sent report to Slack")
        return True
    except Exception as e:
        logger.error(f"Error sending to Slack: {e}")
        return False

def main():
    """メイン処理"""
    logger.info("Starting holdings and P&L calculation")
    
    try:
        # 資産状況・評価損益を計算
        data = calculate_holdings_and_pnl()
        
        # レポート整形
        report = format_report(data)
        
        # コンソール出力
        logger.info("Generated report:")
        print(report)
        
        # Slack通知
        if send_to_slack(report):
            logger.info("Holdings and P&L report completed successfully")
        else:
            logger.warning("Report generated but Slack notification failed")
            
    except Exception as e:
        logger.error(f"Error in main process: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
