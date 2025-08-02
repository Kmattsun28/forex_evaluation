# app/engine/inference_engine.py

import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

class InferenceEngine:
    """
    取引LLMから受信した推論結果を解析・構造化するエンジン
    """
    
    def __init__(self):
        # 取引アクションを抽出するための正規表現パターン
        self.action_patterns = [
            r'(BUY|SELL)\s+([A-Z]{6})',  # "BUY USDJPY", "SELL EURJPY"
            r'([A-Z]{6})\s+(BUY|SELL)',  # "USDJPY BUY", "EURJPY SELL"
            r'ポジション\s*:\s*(買い|売り)\s*([A-Z]{6})',  # 日本語パターン
            r'([A-Z]{6})\s*を\s*(買い|売り)',  # 日本語パターン2
        ]
    
    def parse_inference_response(self, raw_response: str) -> List[Dict[str, Any]]:
        """
        LLMの生レスポンスから構造化された推論アクションを抽出
        
        Args:
            raw_response: LLMからの生レスポンス文字列
            
        Returns:
            推論アクションのリスト [{'action': 'BUY', 'pair': 'USDJPY', 'confidence': 0.8}]
        """
        actions = []
        
        # 複数のパターンで取引アクションを検索
        for pattern in self.action_patterns:
            matches = re.finditer(pattern, raw_response, re.IGNORECASE)
            for match in matches:
                groups = match.groups()
                
                # パターンに応じて action と pair を抽出
                if groups[0].upper() in ['BUY', 'SELL']:
                    action = groups[0].upper()
                    pair = groups[1].upper()
                elif groups[1].upper() in ['BUY', 'SELL']:
                    pair = groups[0].upper()
                    action = groups[1].upper()
                elif groups[0] in ['買い', 'ロング']:
                    action = 'BUY'
                    pair = groups[1].upper() if len(groups) > 1 else None
                elif groups[0] in ['売り', 'ショート']:
                    action = 'SELL'
                    pair = groups[1].upper() if len(groups) > 1 else None
                else:
                    continue
                
                if pair and len(pair) == 6:  # 通貨ペアの妥当性チェック
                    # 信頼度を推定（簡易版）
                    confidence = self._estimate_confidence(raw_response, match.start(), match.end())
                    
                    actions.append({
                        'action': action,
                        'pair': pair,
                        'confidence': confidence,
                        'position_in_text': match.start()
                    })
        
        # 重複を除去し、信頼度でソート
        unique_actions = []
        seen_pairs = set()
        
        for action in sorted(actions, key=lambda x: x['confidence'], reverse=True):
            if action['pair'] not in seen_pairs:
                unique_actions.append({
                    'action': action['action'],
                    'pair': action['pair'],
                    'confidence': action['confidence']
                })
                seen_pairs.add(action['pair'])
        
        return unique_actions
    
    def _estimate_confidence(self, text: str, start_pos: int, end_pos: int) -> float:
        """
        推論の信頼度を推定する（簡易版）
        
        Args:
            text: 全体のテキスト
            start_pos: マッチした部分の開始位置
            end_pos: マッチした部分の終了位置
            
        Returns:
            信頼度スコア (0.0-1.0)
        """
        base_confidence = 0.5
        
        # 周辺テキストを取得
        context_start = max(0, start_pos - 100)
        context_end = min(len(text), end_pos + 100)
        context = text[context_start:context_end].lower()
        
        # ポジティブな表現があれば信頼度を上げる
        positive_keywords = [
            '強く推奨', '確信', '明確', '強気', 'strong', 'confident', 
            'clear', 'bullish', 'bearish', '高い確率'
        ]
        
        for keyword in positive_keywords:
            if keyword in context:
                base_confidence += 0.2
        
        # ネガティブな表現があれば信頼度を下げる
        negative_keywords = [
            '不確実', '疑問', 'uncertain', 'maybe', 'possibly', 
            'might', 'could', '可能性'
        ]
        
        for keyword in negative_keywords:
            if keyword in context:
                base_confidence -= 0.15
        
        # 0.0-1.0の範囲に正規化
        return max(0.0, min(1.0, base_confidence))
    
    def extract_reasoning_summary(self, raw_response: str) -> str:
        """
        推論の要約を抽出する
        
        Args:
            raw_response: LLMからの生レスポンス
            
        Returns:
            推論の要約文字列
        """
        # 簡易版：最初の段落または最初の200文字を要約として使用
        lines = raw_response.strip().split('\n')
        
        # 空行ではない最初の行を探す
        for line in lines:
            if line.strip():
                summary = line.strip()
                if len(summary) > 200:
                    summary = summary[:200] + "..."
                return summary
        
        # フォールバック：最初の200文字
        return raw_response[:200] + "..." if len(raw_response) > 200 else raw_response
