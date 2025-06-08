import pandas as pd
import numpy as np
import fuzzychinese
import re
import json
import os

class FuzzyMatch:
    def __init__(self):
        self.template_path = './resource/客戶訂單資料.xlsx'
        self.load_items()
        self.build_fuzzy_match(self.template_items, self.name_to_id)
    
    def fuzzy_match(self, path):
        ocr_texts, ocr_scores = self.load_ocr_result(path)
        self.fuzzy_match_ocr_single(ocr_texts, ocr_scores)

    def load_items(self):
        """订单资料存在重复品号以及品号下多个品名情况，先处理成独立的词
        处理逻辑：品名按照正斜杠与反斜杠做分隔，品名+单位绑定为一个元组，映射到一个品号id
        如果品名+单位有重复，只保留第一个
        """
        ITEMS = dict()
        NAME_to_ID = dict()
        df = pd.read_excel(self.template_path, engine='openpyxl')
        for index, row in df.iterrows():
            id = row['品號']
            ITEMS.setdefault(id, dict())
            ITEMS[id].setdefault('name', set())
            results = re.split(r'[\\/]', row['品名'])
            unit = row['單位']
            if unit == 'KG':
                unit = '斤'
            for result in results:
                result = result.strip()
                result_unit = (result, unit)
                ITEMS[id]['name'].add(result_unit)
                if result_unit not in NAME_to_ID:
                    NAME_to_ID[result_unit] = id
                elif NAME_to_ID[result_unit] != id:
                    print(f"品名 {result_unit} 重复，请确认品号 {NAME_to_ID[result_unit], id}")
                else:
                    pass
        self.template_items = ITEMS
        self.name_to_id = NAME_to_ID
                
    def build_fuzzy_match(self, ITEMS, NAME_to_ID):
        """
        分别build 品号与品名的模糊匹配器
        """
        self.fcm_name_radical = fuzzychinese.FuzzyChineseMatch(analyzer='radical', ngram_range=(3, 3))
        template_item_name = [tup[0] for tup in list(NAME_to_ID.keys())]
        self.fcm_name_radical.fit(template_item_name)
        self.fcm_name_stroke = fuzzychinese.FuzzyChineseMatch(analyzer='stroke', ngram_range=(3, 3))
        self.fcm_name_stroke.fit(template_item_name)

    def load_ocr_result(self, path):
        """
        """
        with open(path, 'r', encoding='utf-8') as f:
            ocr_result = json.load(f)
        ocr_texts = ocr_result['rec_texts']
        ocr_scores = ocr_result['rec_scores']
        return ocr_texts, ocr_scores
        
    def split_ocr_row(row):
        """
        分割OCR文本行：提取物品、数量、单位。
        参数:
            row (str): 输入字符串，如"東坡肉12×12 42塊"
        返回:
            dict: 包含'item'、'number'、'unit'的字典
        """
        # 定义正则表达式模式：
        # - item: 开头的中文字符序列（\u4e00-\u9fff为Unicode中文范围）
        # - number: 数字、×、空格组成的序列（允许复合结构如"12×12 42"）
        # - unit: 结尾的中文字符序列（单位词）
        pattern = r'^([\u4e00-\u9fff]+)([\d×\s]+)([\u4e00-\u9fff]+)$'
        match = re.match(pattern, row)
        
        if not match:
            # 处理无法匹配的情况（如单位缺失）
            # 尝试仅提取item和number
            fallback_pattern = r'^([\u4e00-\u9fff]+)([\d×\s]+)'
            fallback_match = re.match(fallback_pattern, row)
            if fallback_match:
                return {
                    'item': fallback_match.group(1).strip(),
                    'number': fallback_match.group(2).strip(),
                    'unit': '未知'  # 默认单位
                }
            return {'item': row, 'number': '未知', 'unit': '未知'}  # 完全无法匹配
        
        # 提取并清理组
        item = match.group(1).strip()
        number = match.group(2).strip()
        unit = match.group(3).strip()
        
        return {'item': item, 'number': number, 'unit': unit}

    def fuzzy_match_ocr_single(self, texts, scores):
        """
        """
        for row, score in zip(texts, scores):
            result = self.split_ocr_row(row)
            ocr_item_name = result['item']
            fuzzy_result = fcm_name.transform([ocr_item_name])
            similarity_scores = fcm_name.get_similarity_score()
            print(f"OCR识别结果：{ocr_item_name}，模糊匹配结果：{fuzzy_result}, 相似度分数：{similarity_scores}")
            
    

if __name__ == '__main__':
    ITEMS, NAME_to_ID = load_items()
    fcm_name = build_fuzzy_match(ITEMS, NAME_to_ID)
    ocr_path = './workdir/c1a3f7e2-9893-4fe3-a509-46b31007696c_res.json'
    texts, scores = load_ocr_result(ocr_path)
    fuzzy_match_ocr(fcm_name, texts, scores)
    